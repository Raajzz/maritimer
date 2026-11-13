from django.db.models import Q
from django.http import HttpResponseRedirect
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.enums import InvoiceStatus, PaymentMethod, Role
from apps.core.exceptions import NotFound, ValidationFailed
from apps.core.pagination import StandardPagination, apply_sort
from apps.core.permissions import approved
from apps.core.serializers import MoneyField, NoteSerializer, RequiredNoteSerializer, dec, dt, file_ref, money, org_summary, validated
from apps.documents.models import StoredFile

from . import services
from .models import VendorInvoice


class InvoiceLineSerializer(serializers.Serializer):
    description = serializers.CharField(max_length=300)
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3, required=False)
    unit = serializers.CharField(max_length=16, required=False, allow_blank=True)
    unit_amount = MoneyField(required=False)
    amount = MoneyField()


class InvoiceInputSerializer(serializers.Serializer):
    port_call_id = serializers.IntegerField()
    vendor_request_id = serializers.IntegerField()
    service_category_id = serializers.IntegerField()
    invoice_number = serializers.CharField(max_length=60)
    issue_date = serializers.DateField()
    due_date = serializers.DateField(required=False, allow_null=True)
    currency_code = serializers.CharField(max_length=3)
    subtotal_amount = MoneyField(min_value=0)
    tax_amount = MoneyField(min_value=0, required=False, default="0")
    total_amount = MoneyField(min_value=0)
    file_id = serializers.IntegerField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    lines = InvoiceLineSerializer(many=True, required=False)


class InvoiceUpdateSerializer(InvoiceInputSerializer):
    port_call_id = serializers.IntegerField(required=False)
    vendor_request_id = serializers.IntegerField(required=False)


class MarkPaidSerializer(serializers.Serializer):
    amount = MoneyField(required=False)
    currency_code = serializers.CharField(max_length=3, required=False)
    fx_rate_id = serializers.IntegerField(required=False, allow_null=True)
    paid_at = serializers.DateTimeField(required=False)
    method = serializers.ChoiceField(choices=PaymentMethod.choices, required=False)
    bank_reference = serializers.CharField(required=False, allow_blank=True)


def _resolve_file(user, data):
    if data.get("file_id"):
        stored = StoredFile.objects.filter(pk=data["file_id"], uploaded_by_user=user).first()
        if stored is None:
            raise ValidationFailed("Upload the invoice file first.", {"file_id": ["Unknown file."]})
        data["file"] = stored
    elif "file_id" in data:
        data["file"] = None
    data.pop("file_id", None)
    return data


def invoice_row(inv):
    return {
        "id": inv.pk,
        "port_call": {"id": inv.port_call_id, "reference": inv.port_call.reference, "status": inv.port_call.status},
        "vendor": org_summary(inv.vendor_organization),
        "agent": org_summary(inv.agent_organization),
        "vendor_request_id": inv.vendor_request_id,
        "service_category": {"id": inv.service_category_id, "code": inv.service_category.code, "name": inv.service_category.name},
        "invoice_number": inv.invoice_number,
        "issue_date": inv.issue_date.isoformat(),
        "due_date": inv.due_date.isoformat() if inv.due_date else None,
        "currency_code": inv.currency_id,
        "subtotal_amount": dec(inv.subtotal_amount),
        "tax_amount": dec(inv.tax_amount),
        "total_amount": dec(inv.total_amount),
        "total": money(inv.total_amount, inv.currency_id),
        "status": inv.status,
        "created_at": dt(inv.created_at),
    }


def invoice_detail(inv, request):
    line = services.fda_line_for(inv)
    payment = inv.payments.filter(status="CONFIRMED").order_by("-confirmed_at").first()
    return {
        **invoice_row(inv),
        "lines": [{"line_no": l.line_no, "description": l.description, "quantity": dec(l.quantity), "unit": l.unit,
                   "unit_amount": dec(l.unit_amount), "amount": dec(l.amount)} for l in inv.lines.all()],
        "file": file_ref(inv.file, request),
        "notes": inv.notes,
        "review_note": inv.review_note,
        "reviewed_at": dt(inv.reviewed_at),
        "paid_at": dt(inv.paid_at),
        "fda_line": {"account_id": line.account_id, "version": line.account.version, "line_id": line.pk} if line else None,
        "payment": {"id": payment.pk, "reference": payment.reference, "amount": money(payment.amount, payment.currency_id),
                    "paid_at": dt(payment.paid_at)} if payment else None,
    }


def scoped_invoices(user):
    qs = VendorInvoice.objects.select_related("port_call", "vendor_organization", "agent_organization", "service_category", "file")
    if user.role == Role.ADMIN:
        return qs
    org_id = user.organization_id
    if user.role == Role.MERCHANT:
        return qs.filter(vendor_organization_id=org_id)
    if user.role == Role.AGENT:
        return qs.filter(agent_organization_id=org_id).exclude(status=InvoiceStatus.DRAFT)
    if user.role == Role.OWNER:
        return qs.filter(port_call__owner_organization_id=org_id, status__in=[InvoiceStatus.ACCEPTED, InvoiceStatus.PAID])
    return qs.none()


def get_invoice(user, pk):
    inv = scoped_invoices(user).filter(pk=pk).first()
    if inv is None:
        raise NotFound()
    return inv


ALL_PARTIES = approved(Role.MERCHANT, Role.AGENT, Role.OWNER, Role.ADMIN)


class InvoiceListView(APIView):
    permission_classes = ALL_PARTIES

    def get(self, request):
        qs = scoped_invoices(request.user)
        params = request.query_params
        if params.get("port_call_id"):
            qs = qs.filter(port_call_id=params["port_call_id"])
        if params.get("status"):
            qs = qs.filter(status__in=params["status"].split(","))
        if params.get("vendor_organization_id"):
            qs = qs.filter(vendor_organization_id=params["vendor_organization_id"])
        if params.get("q"):
            q = params["q"]
            qs = qs.filter(Q(invoice_number__icontains=q) | Q(port_call__reference__icontains=q))
        qs = apply_sort(qs, request, {"issue_date": "issue_date", "total_amount": "total_amount", "created_at": "created_at", "id": "id"}, "-issue_date")
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([invoice_row(i) for i in page])

    def post(self, request):
        if request.user.role != Role.MERCHANT:
            raise NotFound()
        data = _resolve_file(request.user, dict(validated(InvoiceInputSerializer, request.data)))
        inv = services.create_invoice(actor=request.user, data=data)
        return Response(invoice_detail(get_invoice(request.user, inv.pk), request), status=status.HTTP_201_CREATED)


class InvoiceDetailView(APIView):
    permission_classes = ALL_PARTIES

    def get(self, request, pk):
        return Response(invoice_detail(get_invoice(request.user, pk), request))

    def put(self, request, pk):
        if request.user.role != Role.MERCHANT:
            raise NotFound()
        data = _resolve_file(request.user, dict(validated(InvoiceUpdateSerializer, request.data, partial=True)))
        services.update_invoice(actor=request.user, invoice=get_invoice(request.user, pk), data=data)
        return Response(invoice_detail(get_invoice(request.user, pk), request))


def _invoice_action(roles, func, serializer=None):
    class _View(APIView):
        permission_classes = approved(*roles)

        def post(self, request, pk):
            kwargs = validated(serializer, request.data) if serializer else {}
            func(actor=request.user, invoice=get_invoice(request.user, pk), **kwargs)
            return Response(invoice_detail(get_invoice(request.user, pk), request))

    return _View


InvoiceIssueView = _invoice_action([Role.MERCHANT], services.issue_invoice)
InvoiceAcceptView = _invoice_action([Role.AGENT], services.accept_invoice, NoteSerializer)
InvoiceRejectView = _invoice_action([Role.AGENT], services.reject_invoice, RequiredNoteSerializer)
InvoiceReopenView = _invoice_action([Role.MERCHANT], services.reopen_invoice)
InvoiceVoidView = _invoice_action([Role.MERCHANT], services.void_invoice)


class InvoiceMarkPaidView(APIView):
    permission_classes = approved(Role.AGENT)

    def post(self, request, pk):
        data = validated(MarkPaidSerializer, request.data)
        services.pay_invoice(actor=request.user, invoice=get_invoice(request.user, pk), data=dict(data))
        return Response(invoice_detail(get_invoice(request.user, pk), request))


class InvoiceFileView(APIView):
    permission_classes = ALL_PARTIES

    def get(self, request, pk):
        inv = get_invoice(request.user, pk)
        if inv.file_id is None:
            raise NotFound("No file attached.")
        ref = file_ref(inv.file, request)
        if request.query_params.get("redirect") == "false":
            return Response({"file": ref})
        return HttpResponseRedirect(ref["download_url"])
