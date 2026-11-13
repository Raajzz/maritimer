from django.http import HttpResponse, HttpResponseRedirect
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.enums import DISPUTE_LIVE, AccountKind, Role
from apps.core.exceptions import NotFound
from apps.core.permissions import approved
from apps.core.serializers import MoneyField, NoteSerializer, RequiredNoteSerializer, dec, dt, file_ref, money, user_summary, validated
from apps.portcalls.selectors import get_port_call_for, party_role, port_calls_for

from . import services
from .models import DisbursementAccount


class LineItemSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False, allow_null=True)
    service_category_id = serializers.IntegerField(required=False, allow_null=True)
    description = serializers.CharField(max_length=300, required=False, allow_blank=True)
    vendor_organization_id = serializers.IntegerField(required=False, allow_null=True)
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3, required=False)
    unit = serializers.CharField(max_length=16, required=False, allow_blank=True)
    local_amount = MoneyField(required=False, allow_null=True)
    local_currency_code = serializers.CharField(max_length=3, required=False)
    fx_rate_id = serializers.IntegerField(required=False, allow_null=True)
    amount = MoneyField(required=False, allow_null=True)
    pda_line_item_id = serializers.IntegerField(required=False, allow_null=True)
    vendor_invoice_id = serializers.IntegerField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class LineItemsSerializer(serializers.Serializer):
    line_items = LineItemSerializer(many=True)


class CreatePdaSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    line_items = LineItemSerializer(many=True, required=False)


class GenerateFdaSerializer(serializers.Serializer):
    fx_rate_ids = serializers.DictField(child=serializers.IntegerField(), required=False)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


def line_data(line):
    return {
        "id": line.pk,
        "line_no": line.line_no,
        "service_category_id": line.service_category_id,
        "service_category": {"id": line.service_category_id, "code": line.service_category.code, "name": line.service_category.name},
        "description": line.description,
        "vendor_organization_id": line.vendor_organization_id,
        "vendor_name": line.vendor_organization.legal_name if line.vendor_organization_id else None,
        "quantity": dec(line.quantity),
        "unit": line.unit,
        "local_amount": dec(line.local_amount),
        "local_currency_code": line.local_currency_id,
        "fx_rate_id": line.fx_rate_id,
        "fx_rate_applied": dec(line.fx_rate_applied),
        "amount": dec(line.amount),
        "pda_line_item_id": line.pda_line_item_id,
        "vendor_invoice_id": line.vendor_invoice_id,
        "vendor_invoice_number": line.vendor_invoice.invoice_number if line.vendor_invoice_id else None,
        "supersedes_line_item_id": line.supersedes_line_item_id,
        "is_adjustment": line.is_adjustment,
        "source_dispute_id": line.source_dispute_id,
        "notes": line.notes,
    }


def account_summary(acc):
    return {
        "id": acc.pk,
        "port_call_id": acc.port_call_id,
        "kind": acc.kind,
        "version": acc.version,
        "is_current": acc.is_current,
        "reference": acc.reference,
        "status": acc.status,
        "currency_code": acc.currency_id,
        "total": money(acc.total_amount, acc.currency_id),
        "issued_at": dt(acc.issued_at),
        "finalized_at": dt(acc.finalized_at),
        "owner_responded_at": dt(acc.owner_responded_at),
        "created_at": dt(acc.created_at),
    }


def account_detail(acc):
    from apps.disputes.models import Dispute

    lines = acc.line_items.select_related("service_category", "vendor_organization", "vendor_invoice").order_by("line_no")
    data = {
        **account_summary(acc),
        "supersedes_id": acc.supersedes_id,
        "prepared_by": user_summary(acc.prepared_by_user),
        "owner_responded_by": user_summary(acc.owner_responded_by_user),
        "owner_response_note": acc.owner_response_note,
        "fx_policy_note": acc.fx_policy_note,
        "notes": acc.notes,
        "line_items": [line_data(l) for l in lines],
        "totals": {"total": money(acc.total_amount, acc.currency_id), "line_count": len(lines)},
    }
    if acc.kind == AccountKind.FDA:
        data["variance"] = services.variance(acc)
        for row in data["variance"]["lines"]:
            for key in ("pda_amount", "fda_amount", "variance"):
                row[key] = dec(row[key])
        for key in ("pda_total", "fda_total", "total_variance"):
            data["variance"][key] = dec(data["variance"][key])
        disputes = Dispute.objects.filter(port_call=acc.port_call).select_related("line_item").order_by("-created_at")
        data["disputes"] = [
            {"id": d.pk, "reference": d.reference, "status": d.status, "line_item_id": d.line_item_id,
             "line_description": d.line_item.description, "is_live": d.status in DISPUTE_LIVE, "created_at": dt(d.created_at)}
            for d in disputes
        ]
    return data


def get_account(user, pk, *, allow_merchant=False):
    acc = DisbursementAccount.objects.select_related("port_call").filter(pk=pk).first()
    if acc is None or not port_calls_for(user).filter(pk=acc.port_call_id).exists():
        raise NotFound()
    if not allow_merchant and party_role(user, acc.port_call) == "MERCHANT":
        raise NotFound()
    return acc


PARTIES = approved(Role.OWNER, Role.AGENT, Role.ADMIN)


class CurrentAccountView(APIView):
    permission_classes = PARTIES
    kind = None

    def get(self, request, pk):
        pc = get_port_call_for(request.user, pk)
        acc = services.current_account(pc, self.kind)
        if acc is None:
            raise NotFound(f"No {self.kind} yet.")
        return Response(account_detail(acc))


class CurrentPdaView(CurrentAccountView):
    kind = AccountKind.PDA

    def post(self, request, pk):
        if request.user.role != Role.AGENT:
            raise NotFound()
        data = validated(CreatePdaSerializer, request.data)
        pc = get_port_call_for(request.user, pk)
        acc = services.create_pda(actor=request.user, port_call=pc, notes=data["notes"], line_items=data.get("line_items"))
        return Response(account_detail(acc), status=status.HTTP_201_CREATED)


class CurrentFdaView(CurrentAccountView):
    kind = AccountKind.FDA


class AccountVersionsView(APIView):
    permission_classes = PARTIES
    kind = None

    def get(self, request, pk):
        pc = get_port_call_for(request.user, pk)
        qs = DisbursementAccount.objects.filter(port_call=pc, kind=self.kind).order_by("-version")
        return Response([account_summary(a) for a in qs])


class PdaVersionsView(AccountVersionsView):
    kind = AccountKind.PDA


class FdaVersionsView(AccountVersionsView):
    kind = AccountKind.FDA


class GenerateFdaView(APIView):
    permission_classes = approved(Role.AGENT)

    def post(self, request, pk):
        data = validated(GenerateFdaSerializer, request.data)
        pc = get_port_call_for(request.user, pk)
        acc, warnings = services.generate_fda(actor=request.user, port_call=pc, fx_rate_ids=data.get("fx_rate_ids"), notes=data["notes"])
        return Response({**account_detail(acc), "warnings": warnings}, status=status.HTTP_201_CREATED)


class AccountDetailView(APIView):
    permission_classes = PARTIES

    def get(self, request, pk):
        return Response(account_detail(get_account(request.user, pk)))


class AccountLinesView(APIView):
    permission_classes = approved(Role.AGENT)

    def put(self, request, pk):
        data = validated(LineItemsSerializer, request.data)
        acc = services.replace_lines(actor=request.user, account=get_account(request.user, pk), lines=data["line_items"])
        return Response(account_detail(acc))


def _action_view(roles, func, serializer=None, arg_map=None):
    class _View(APIView):
        permission_classes = approved(*roles)

        def post(self, request, pk):
            kwargs = {}
            if serializer is not None:
                data = validated(serializer, request.data)
                kwargs = {(arg_map or {}).get(k, k): v for k, v in data.items()}
            result = func(actor=request.user, account=get_account(request.user, pk), **kwargs)
            acc = result[0] if isinstance(result, tuple) else result
            acc.refresh_from_db()
            return Response(account_detail(acc))

    return _View


AccountIssueView = _action_view([Role.AGENT], services.issue)
AccountApproveView = _action_view([Role.OWNER], services.approve_pda, NoteSerializer)
AccountRejectView = _action_view([Role.OWNER], services.reject_pda, RequiredNoteSerializer)
AccountAcceptView = _action_view([Role.OWNER], services.accept_fda, NoteSerializer)
AccountReviseView = _action_view([Role.AGENT], services.revise)
AccountFinalizeView = _action_view([Role.AGENT], services.finalize_fda)
AccountDiscardView = _action_view([Role.AGENT], services.discard)


def pdf_response(request, doc, data, filename):
    """Cached document → 302 to a short-lived URL (or JSON with ?redirect=false). Preview → PDF bytes."""
    if doc is not None:
        ref = file_ref(doc.file, request)
        if request.query_params.get("redirect") == "false":
            return Response({"file": ref, "cached": True})
        return HttpResponseRedirect(ref["download_url"])
    response = HttpResponse(data, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


class AccountPdfView(APIView):
    permission_classes = PARTIES

    def get(self, request, pk):
        from apps.documents.pdf import account_pdf

        acc = get_account(request.user, pk)
        doc, data = account_pdf(acc, user=request.user)
        return pdf_response(request, doc, data, f"{acc.reference}-{acc.status.lower()}-preview.pdf")
