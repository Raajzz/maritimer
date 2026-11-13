from decimal import Decimal

from django.db.models import Count, DecimalField, IntegerField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.enums import (
    DISPUTE_LIVE,
    PIPELINE_GROUPS,
    AccountKind,
    AccountStatus,
    PaymentKind,
    PaymentStatus,
    PortCallStatus,
    RequestStatus,
    RequestType,
    Role,
    SettlementStatus,
)
from apps.core.exceptions import NotFound
from apps.core.models import AuditLog
from apps.core.pagination import StandardPagination, apply_sort
from apps.core.permissions import approved
from apps.core.serializers import ReasonSerializer, dt, money, org_summary, user_summary, validated

from . import services
from .selectors import get_port_call_for, party_role, port_calls_for

ZERO = Value(Decimal("0.00"), output_field=DecimalField(max_digits=18, decimal_places=2))


def with_financials(qs):
    from apps.disbursements.models import DisbursementAccount
    from apps.disputes.models import Dispute
    from apps.payments.models import Payment

    def current_total(kind):
        return Subquery(
            DisbursementAccount.objects.filter(port_call=OuterRef("pk"), kind=kind, is_current=True).values("total_amount")[:1]
        )

    def current_field(kind, field):
        return Subquery(DisbursementAccount.objects.filter(port_call=OuterRef("pk"), kind=kind, is_current=True).values(field)[:1])

    advances = (
        Payment.objects.filter(port_call=OuterRef("pk"), kind=PaymentKind.ADVANCE, status=PaymentStatus.CONFIRMED)
        .values("port_call").annotate(s=Sum("settlement_amount")).values("s")
    )
    settled = (
        Payment.objects.filter(port_call=OuterRef("pk"), kind__in=[PaymentKind.BALANCE, PaymentKind.REFUND], status=PaymentStatus.CONFIRMED)
        .values("port_call").annotate(s=Sum("settlement_amount")).values("s")
    )
    disputes = Dispute.objects.filter(port_call=OuterRef("pk"), status__in=DISPUTE_LIVE).values("port_call").annotate(c=Count("id")).values("c")
    return qs.select_related("settlement").annotate(
        pda_total=current_total(AccountKind.PDA),
        pda_status=current_field(AccountKind.PDA, "status"),
        fda_total=current_total(AccountKind.FDA),
        fda_status=current_field(AccountKind.FDA, "status"),
        advance_sum=Coalesce(Subquery(advances, output_field=DecimalField(max_digits=18, decimal_places=2)), ZERO),
        settled_sum=Coalesce(Subquery(settled, output_field=DecimalField(max_digits=18, decimal_places=2)), ZERO),
        open_dispute_count=Coalesce(Subquery(disputes, output_field=IntegerField()), Value(0)),
    )


def _settlement_summary(pc):
    settlement = getattr(pc, "settlement", None)
    if settlement is None:
        return None
    paid = getattr(pc, "settled_sum", None)
    if paid is None:
        from apps.payments.services import outstanding

        remaining = outstanding(settlement)
    else:
        remaining = abs(settlement.balance) - paid
    return {
        "id": settlement.pk,
        "reference": settlement.reference,
        "direction": settlement.direction,
        "status": settlement.status,
        "balance": money(settlement.balance, settlement.currency_id),
        "outstanding": money(remaining, settlement.currency_id),
    }


def port_call_row(pc, *, restricted=False):
    row = {
        "id": pc.pk,
        "reference": pc.reference,
        "status": pc.status,
        "status_changed_at": dt(pc.status_changed_at),
        "vessel": {"id": pc.vessel_id, "name": pc.vessel.name, "imo_number": pc.vessel.imo_number, "vessel_type": pc.vessel.vessel_type},
        "port": {"id": pc.port_id, "name": pc.port.name, "unlocode": pc.port.unlocode},
        "owner": org_summary(pc.owner_organization),
        "agent": org_summary(pc.agent_organization),
        "eta": dt(pc.eta),
        "etd": dt(pc.etd),
        "ata": dt(pc.ata),
        "atd": dt(pc.atd),
        "berth": pc.berth,
    }
    if restricted:  # merchants never see owner/agent financials
        row.pop("owner")
        return row
    cur = pc.settlement_currency_id
    row.update(
        settlement_currency_code=cur,
        pda_total=money(pc.pda_total, cur) if getattr(pc, "pda_total", None) is not None else None,
        fda_total=money(pc.fda_total, cur) if getattr(pc, "fda_total", None) is not None else None,
        advance_total=money(getattr(pc, "advance_sum", Decimal("0")), cur),
        open_disputes=getattr(pc, "open_dispute_count", 0),
        settlement=_settlement_summary(pc),
    )
    return row


def allowed_actions(user, pc) -> list[str]:
    """Actions the UI should offer this actor now (derived from STATE_MACHINES.md; the server re-checks)."""
    from apps.disbursements.services import current_account
    from apps.ratings.models import Rating

    role = party_role(user, pc)
    s = pc.status
    actions = []
    pda = current_account(pc, AccountKind.PDA)
    fda = current_account(pc, AccountKind.FDA)
    settlement = getattr(pc, "settlement", None) if hasattr(pc, "settlement") else None
    if role == "AGENT":
        if s == PortCallStatus.PDA_PENDING:
            if pda is None or pda.status == AccountStatus.REJECTED:
                actions.append("pda.create")
            elif pda.status == AccountStatus.DRAFT:
                actions += ["pda.edit", "pda.issue"]
        if s == PortCallStatus.PDA_SENT and pda and pda.status == AccountStatus.ISSUED:
            actions.append("pda.revise")
        if s in (PortCallStatus.PDA_APPROVED, PortCallStatus.ADVANCE_RECEIVED):
            actions.append("arrive")
        if s == PortCallStatus.IN_PORT:
            actions.append("depart")
        if s not in (PortCallStatus.FDA_FINAL, PortCallStatus.SETTLED, PortCallStatus.CLOSED, PortCallStatus.CANCELLED):
            actions += ["vendor_request.create", "edit"]
        if s == PortCallStatus.DEPARTED and (fda is None or (fda.status == AccountStatus.DRAFT and fda.version == 1)):
            actions.append("fda.generate")
        if fda and fda.status == AccountStatus.DRAFT:
            actions += ["fda.edit", "fda.issue"]
            if fda.version > 1:
                actions.append("fda.discard")
        if fda and fda.status == AccountStatus.ISSUED and s in (PortCallStatus.FDA_ISSUED, PortCallStatus.DISPUTED):
            actions.append("fda.revise")
            if s == PortCallStatus.FDA_ISSUED:
                actions.append("fda.finalize")
        if s == PortCallStatus.DISPUTED:
            actions.append("dispute.respond")
        if settlement and settlement.status != SettlementStatus.CLOSED and settlement.direction == "REFUND_DUE":
            actions.append("settlement.record_refund")
        if settlement and settlement.status != SettlementStatus.CLOSED:
            actions += ["payment.confirm", "settlement.force_close"]
        if s in (PortCallStatus.PDA_APPROVED, PortCallStatus.ADVANCE_RECEIVED, PortCallStatus.IN_PORT, PortCallStatus.DEPARTED):
            actions.append("payment.confirm")
        if s == PortCallStatus.SETTLED:
            actions.append("close")
        if s in services.PORT_CALL_MACHINE.table["cancel"].sources:
            actions.append("cancel")
    elif role == "OWNER":
        if s == PortCallStatus.PDA_SENT:
            actions += ["pda.approve", "pda.reject"]
        if s in (PortCallStatus.PDA_APPROVED, PortCallStatus.ADVANCE_RECEIVED, PortCallStatus.IN_PORT, PortCallStatus.DEPARTED):
            actions.append("advance.record")
        if fda and fda.status == AccountStatus.ISSUED and s in (PortCallStatus.FDA_ISSUED, PortCallStatus.DISPUTED):
            actions += ["dispute.open"]
            if fda.owner_responded_at is None:
                actions.append("fda.accept")
        if settlement and settlement.status != SettlementStatus.CLOSED:
            if settlement.direction == "BALANCE_DUE":
                actions.append("settlement.pay_balance")
            else:
                actions.append("payment.confirm")
        if s in (PortCallStatus.SETTLED, PortCallStatus.CLOSED) and not Rating.objects.filter(port_call=pc, rater_organization_id=user.organization_id).exists():
            actions.append("rate")
        if s in (PortCallStatus.PDA_PENDING, PortCallStatus.PDA_SENT):
            actions.append("cancel")
    elif role == "MERCHANT":
        if s not in (PortCallStatus.FDA_FINAL, PortCallStatus.SETTLED, PortCallStatus.CLOSED, PortCallStatus.CANCELLED):
            actions.append("invoice.create")
    elif role == "ADMIN" and s in services.PORT_CALL_MACHINE.table["cancel"].sources:
        actions.append("cancel")
    return sorted(set(actions))


def port_call_detail(request, pc):
    from apps.chat.models import ChatThread
    from apps.disbursements.services import current_account
    from apps.documents.models import GeneratedDocument
    from apps.invoices.models import VendorInvoice
    from apps.requests.models import Request

    user = request.user
    role = party_role(user, pc)
    restricted = role == "MERCHANT"
    data = port_call_row(pc, restricted=restricted)
    data.update(
        cargo_type={"id": pc.cargo_type_id, "name": pc.cargo_type.name},
        notes=pc.notes,
        cancelled_reason=pc.cancelled_reason,
        closed_at=dt(pc.closed_at),
        request_id=pc.request_id,
        my_role=role,
        allowed_actions=allowed_actions(user, pc),
    )
    if restricted:
        threads = ChatThread.objects.filter(port_call=pc, participants__organization_id=user.organization_id)
        data["chat_thread_ids"] = list(threads.values_list("pk", flat=True))
        data["counts"] = {
            "vendor_requests": Request.objects.filter(port_call=pc, to_organization_id=user.organization_id).count(),
            "invoices": VendorInvoice.objects.filter(port_call=pc, vendor_organization_id=user.organization_id).count(),
        }
        return data

    def account_summary(acc):
        if acc is None:
            return None
        return {"id": acc.pk, "reference": acc.reference, "version": acc.version, "status": acc.status,
                "total": money(acc.total_amount, acc.currency_id), "issued_at": dt(acc.issued_at),
                "owner_responded_at": dt(acc.owner_responded_at)}

    thread = ChatThread.objects.filter(port_call=pc, kind="PORT_CALL").first()
    invoices = VendorInvoice.objects.filter(port_call=pc)
    if role == "OWNER":
        invoices = invoices.filter(status__in=["ACCEPTED", "PAID"])
    data.update(
        pda=account_summary(current_account(pc, AccountKind.PDA)),
        fda=account_summary(current_account(pc, AccountKind.FDA)),
        chat_thread_id=thread.pk if thread else None,
        counts={
            "vendor_requests": Request.objects.filter(port_call=pc, request_type=RequestType.VENDOR_SERVICE).count() if role in ("AGENT", "ADMIN") else 0,
            "invoices": invoices.count(),
            "documents": GeneratedDocument.objects.filter(port_call=pc).count(),
            "pending_payments": pc.payments.filter(status=PaymentStatus.PENDING).count(),
        },
    )
    return data


STATUS_SORTS = {"eta": "eta", "reference": "reference", "status_changed_at": "status_changed_at", "created_at": "created_at", "id": "id"}


class PortCallListView(APIView):
    permission_classes = approved(Role.OWNER, Role.AGENT, Role.MERCHANT, Role.ADMIN)

    def get(self, request):
        qs = port_calls_for(request.user)
        params = request.query_params
        if params.get("status"):
            qs = qs.filter(status__in=params["status"].split(","))
        if params.get("status_group") in PIPELINE_GROUPS:
            qs = qs.filter(status__in=PIPELINE_GROUPS[params["status_group"]])
        for key in ("vessel_id", "port_id", "owner_organization_id", "agent_organization_id"):
            if params.get(key):
                qs = qs.filter(**{key: params[key]})
        if params.get("q"):
            q = params["q"]
            qs = qs.filter(Q(reference__icontains=q) | Q(vessel__name__icontains=q) | Q(port__name__icontains=q))
        restricted = request.user.role == Role.MERCHANT
        if not restricted:
            qs = with_financials(qs)
        qs = apply_sort(qs, request, STATUS_SORTS, "-status_changed_at")
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([port_call_row(pc, restricted=restricted) for pc in page])


class PortCallUpdateSerializer(serializers.Serializer):
    eta = serializers.DateTimeField(required=False)
    etd = serializers.DateTimeField(required=False)
    berth = serializers.CharField(max_length=100, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)


def _detail(request, pk):
    qs = port_calls_for(request.user)
    if request.user.role != Role.MERCHANT:
        qs = with_financials(qs)
    pc = qs.filter(pk=pk).first()
    if pc is None:
        raise NotFound()
    return port_call_detail(request, pc)


class PortCallDetailView(APIView):
    permission_classes = approved(Role.OWNER, Role.AGENT, Role.MERCHANT, Role.ADMIN)

    def get(self, request, pk):
        return Response(_detail(request, pk))

    def patch(self, request, pk):
        data = validated(PortCallUpdateSerializer, request.data, partial=True)
        services.update_port_call(actor=request.user, port_call=get_port_call_for(request.user, pk), data=data)
        return Response(_detail(request, pk))


class ArriveSerializer(serializers.Serializer):
    ata = serializers.DateTimeField()


class DepartSerializer(serializers.Serializer):
    atd = serializers.DateTimeField()


class PortCallArriveView(APIView):
    permission_classes = approved(Role.AGENT)

    def post(self, request, pk):
        data = validated(ArriveSerializer, request.data)
        services.arrive(actor=request.user, port_call=get_port_call_for(request.user, pk), ata=data["ata"])
        return Response(_detail(request, pk))


class PortCallDepartView(APIView):
    permission_classes = approved(Role.AGENT)

    def post(self, request, pk):
        data = validated(DepartSerializer, request.data)
        services.depart(actor=request.user, port_call=get_port_call_for(request.user, pk), atd=data["atd"])
        return Response(_detail(request, pk))


class PortCallCancelView(APIView):
    permission_classes = approved(Role.AGENT, Role.OWNER, Role.ADMIN)

    def post(self, request, pk):
        data = validated(ReasonSerializer, request.data)
        services.cancel(actor=request.user, port_call=get_port_call_for(request.user, pk), reason=data["reason"])
        return Response(_detail(request, pk))


class PortCallCloseView(APIView):
    permission_classes = approved(Role.AGENT)

    def post(self, request, pk):
        services.close(actor=request.user, port_call=get_port_call_for(request.user, pk))
        return Response(_detail(request, pk))


def audit_row(entry):
    return {
        "id": entry.pk,
        "action": entry.action,
        "actor": user_summary(entry.actor_user),
        "actor_role": entry.actor_role,
        "entity_type": entry.entity_type,
        "entity_id": entry.entity_id,
        "port_call_id": entry.port_call_id,
        "from_state": entry.from_state,
        "to_state": entry.to_state,
        "changes": entry.changes,
        "metadata": entry.metadata,
        "created_at": dt(entry.created_at),
    }


class PortCallTimelineView(APIView):
    permission_classes = approved(Role.OWNER, Role.AGENT, Role.ADMIN)

    def get(self, request, pk):
        pc = get_port_call_for(request.user, pk)
        qs = AuditLog.objects.filter(port_call=pc).select_related("actor_user").order_by("-created_at", "-id")
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([audit_row(e) for e in page])


class PortCallVendorRequestsView(APIView):
    permission_classes = approved(Role.AGENT, Role.MERCHANT, Role.ADMIN)

    def get(self, request, pk):
        from apps.requests.views import request_row, scoped_requests

        pc = get_port_call_for(request.user, pk)
        qs = scoped_requests(request.user).filter(port_call=pc, request_type=RequestType.VENDOR_SERVICE).order_by("-created_at")
        return Response([request_row(r) for r in qs])


class PortCallDocumentsView(APIView):
    permission_classes = approved(Role.OWNER, Role.AGENT, Role.ADMIN)

    def get(self, request, pk):
        from apps.core.serializers import file_ref
        from apps.documents.models import GeneratedDocument
        from apps.invoices.models import VendorInvoice

        pc = get_port_call_for(request.user, pk)
        rows = []
        for doc in GeneratedDocument.objects.filter(port_call=pc).select_related("file", "disbursement_account", "settlement").order_by("-generated_at"):
            rows.append({
                "document_type": doc.document_type,
                "reference": doc.disbursement_account.reference if doc.disbursement_account_id else doc.settlement.reference,
                "version": doc.disbursement_account.version if doc.disbursement_account_id else None,
                "entity_status": doc.entity_status,
                "file": file_ref(doc.file, request),
                "generated_at": dt(doc.generated_at),
            })
        for inv in VendorInvoice.objects.filter(port_call=pc, status__in=["ACCEPTED", "PAID"], file__isnull=False).select_related("file", "vendor_organization"):
            rows.append({
                "document_type": "VENDOR_INVOICE",
                "reference": inv.invoice_number,
                "version": None,
                "entity_status": inv.status,
                "vendor": org_summary(inv.vendor_organization),
                "file": file_ref(inv.file, request),
                "generated_at": dt(inv.created_at),
            })
        return Response(rows)


__all__ = ["RequestStatus"]
