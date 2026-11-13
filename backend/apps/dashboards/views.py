"""Role dashboards (API.md §16). Read-only aggregates."""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.enums import (
    DISPUTE_LIVE,
    PIPELINE_GROUPS,
    AccountKind,
    AccountStatus,
    InvoiceStatus,
    PaymentKind,
    PaymentStatus,
    PortCallStatus,
    RequestStatus,
    RequestType,
    Role,
    SettlementDirection,
    SettlementStatus,
)
from apps.core.exceptions import NotFound
from apps.core.models import AuditLog
from apps.core.permissions import approved
from apps.core.serializers import money
from apps.portcalls.selectors import port_calls_for
from apps.portcalls.views import audit_row, port_call_row, with_financials

ACTIVE_EXCLUDE = [PortCallStatus.CLOSED, PortCallStatus.CANCELLED]


def _sum(qs, field="amount"):
    return qs.aggregate(s=Sum(field))["s"] or Decimal("0.00")


def _outstanding_by_direction(port_calls, direction):
    from apps.payments.services import outstanding

    total = Decimal("0.00")
    for pc in port_calls.filter(settlement__direction=direction, settlement__status__in=[SettlementStatus.OPEN, SettlementStatus.PARTIALLY_PAID]).select_related("settlement"):
        total += outstanding(pc.settlement)
    return total


def agent_dashboard(user):
    from apps.disbursements.models import DisbursementAccount
    from apps.disputes.models import Dispute
    from apps.invoices.models import VendorInvoice
    from apps.payments.models import Payment
    from apps.requests.models import Request
    from apps.requests.views import request_row

    org_id = user.organization_id
    calls = port_calls_for(user)
    active = with_financials(calls.exclude(status__in=ACTIVE_EXCLUDE))
    pipeline = {"requested": [request_row(r) for r in Request.objects.filter(
        to_organization_id=org_id, request_type=RequestType.PORT_CALL, status=RequestStatus.PENDING
    ).select_related("from_organization", "to_organization", "port_call", "port_call_detail__vessel", "port_call_detail__port").order_by("created_at")]}
    for group, statuses in PIPELINE_GROUPS.items():
        qs = active.filter(status__in=statuses).order_by("eta") if group != "settled" else with_financials(
            calls.filter(status__in=statuses).filter(Q(closed_at__isnull=True) | Q(closed_at__gte=timezone.now() - timedelta(days=30)))
        ).order_by("-status_changed_at")
        pipeline[group] = [port_call_row(pc) for pc in qs[:50]]

    now = timezone.now()
    attention = []
    for acc in DisbursementAccount.objects.filter(port_call__agent_organization_id=org_id, kind=AccountKind.PDA, status=AccountStatus.DRAFT,
                                                   is_current=True, created_at__lt=now - timedelta(hours=24)).select_related("port_call"):
        attention.append({"type": "PDA_DRAFT_STALE", "port_call": {"id": acc.port_call_id, "reference": acc.port_call.reference},
                          "message": f"PDA draft {acc.reference} not issued for over 24h."})
    for pc in calls.filter(status__in=[PortCallStatus.IN_PORT, PortCallStatus.DEPARTED]).exclude(
        payments__kind=PaymentKind.ADVANCE, payments__status=PaymentStatus.CONFIRMED
    ):
        attention.append({"type": "NO_ADVANCE", "port_call": {"id": pc.pk, "reference": pc.reference},
                          "message": "Vessel is in port without a confirmed advance."})
    for acc in DisbursementAccount.objects.filter(port_call__agent_organization_id=org_id, kind=AccountKind.FDA, status=AccountStatus.ISSUED,
                                                   is_current=True, owner_responded_at__isnull=True, issued_at__lt=now - timedelta(days=7)).select_related("port_call"):
        attention.append({"type": "FDA_SILENT", "port_call": {"id": acc.port_call_id, "reference": acc.port_call.reference},
                          "message": "FDA issued over 7 days ago with no owner response."})
    for d in Dispute.objects.filter(port_call__agent_organization_id=org_id, status__in=DISPUTE_LIVE, created_at__lt=now - timedelta(days=3)).select_related("port_call"):
        attention.append({"type": "DISPUTE_AGING", "port_call": {"id": d.port_call_id, "reference": d.port_call.reference},
                          "message": f"Dispute {d.reference} open for over 3 days."})
    for inv in VendorInvoice.objects.filter(agent_organization_id=org_id, status=InvoiceStatus.ISSUED, updated_at__lt=now - timedelta(days=2)).select_related("port_call"):
        attention.append({"type": "INVOICE_WAITING", "port_call": {"id": inv.port_call_id, "reference": inv.port_call.reference},
                          "message": f"Invoice {inv.invoice_number} awaiting review for over 2 days."})
    pending_confirmations = Payment.objects.filter(payee_organization_id=org_id, status=PaymentStatus.PENDING).count()

    return {
        "pipeline": pipeline,
        "kpis": {
            "active_calls": active.count(),
            "pending_requests": len(pipeline["requested"]),
            "open_disputes": Dispute.objects.filter(port_call__agent_organization_id=org_id, status__in=DISPUTE_LIVE).count(),
            "invoices_awaiting_review": VendorInvoice.objects.filter(agent_organization_id=org_id, status=InvoiceStatus.ISSUED).count(),
            "payments_to_confirm": pending_confirmations,
            "outstanding_balance_due": money(_outstanding_by_direction(calls, SettlementDirection.BALANCE_DUE), "USD"),
            "outstanding_refund_due": money(_outstanding_by_direction(calls, SettlementDirection.REFUND_DUE), "USD"),
        },
        "attention": attention,
    }


def owner_dashboard(user):
    from apps.disbursements.models import DisbursementAccount
    from apps.payments.models import Payment, Settlement
    from apps.ratings.models import Rating
    from apps.requests.models import Request
    from apps.requests.views import request_row
    from apps.vessels.models import Vessel
    from apps.vessels.views import vessel_data

    org_id = user.organization_id
    calls = with_financials(port_calls_for(user))
    vessels = []
    for vessel in Vessel.objects.filter(owner_organization_id=org_id, deleted_at__isnull=True).order_by("name"):
        active = calls.filter(vessel=vessel).exclude(status__in=ACTIVE_EXCLUDE).order_by("eta").first()
        vessels.append({"vessel": vessel_data(vessel), "active_call": port_call_row(active) if active else None})
    by_status = dict(port_calls_for(user).values_list("status").annotate(c=Count("id")).values_list("status", "c"))

    pending = []
    for pc in calls.filter(status=PortCallStatus.PDA_SENT):
        pending.append({"type": "APPROVE_PDA", "port_call": port_call_row(pc)})
    for pc in calls.filter(status=PortCallStatus.PDA_APPROVED):
        pending.append({"type": "RECORD_ADVANCE", "port_call": port_call_row(pc)})
    reviewed = DisbursementAccount.objects.filter(port_call__owner_organization_id=org_id, kind=AccountKind.FDA, status=AccountStatus.ISSUED,
                                                  is_current=True, owner_responded_at__isnull=True).values_list("port_call_id", flat=True)
    for pc in calls.filter(pk__in=list(reviewed)):
        pending.append({"type": "REVIEW_FDA", "port_call": port_call_row(pc)})
    for s in Settlement.objects.filter(port_call__owner_organization_id=org_id, status__in=[SettlementStatus.OPEN, SettlementStatus.PARTIALLY_PAID]):
        kind = "PAY_BALANCE" if s.direction == SettlementDirection.BALANCE_DUE else "CONFIRM_REFUND"
        pending.append({"type": kind, "port_call": port_call_row(calls.get(pk=s.port_call_id))})
    for p in Payment.objects.filter(payee_organization_id=org_id, status=PaymentStatus.PENDING, kind=PaymentKind.REFUND):
        pending.append({"type": "CONFIRM_REFUND", "port_call": port_call_row(calls.get(pk=p.port_call_id)), "payment_id": p.pk})
    rated = set(Rating.objects.filter(rater_organization_id=org_id).values_list("port_call_id", flat=True))
    for pc in calls.filter(status__in=[PortCallStatus.SETTLED, PortCallStatus.CLOSED]).exclude(pk__in=rated):
        pending.append({"type": "RATE_AGENT", "port_call": port_call_row(pc)})

    outgoing = Request.objects.filter(from_organization_id=org_id).select_related(
        "from_organization", "to_organization", "port_call", "port_call_detail__vessel", "port_call_detail__port"
    ).order_by("-created_at")[:20]
    recent = AuditLog.objects.filter(port_call__owner_organization_id=org_id).select_related("actor_user").order_by("-created_at")[:20]
    return {
        "vessels": vessels,
        "calls_by_status": by_status,
        "pending_actions": pending,
        "outgoing_requests": [request_row(r) for r in outgoing],
        "recent_activity": [audit_row(e) for e in recent],
    }


def merchant_dashboard(user):
    from apps.chat.models import ChatThread
    from apps.invoices.models import VendorInvoice
    from apps.payments.models import Payment
    from apps.payments.views import payment_data
    from apps.portcalls.views import port_call_row as pc_row
    from apps.requests.models import Request
    from apps.requests.views import request_row

    org_id = user.organization_id
    base = Request.objects.filter(to_organization_id=org_id, request_type=RequestType.VENDOR_SERVICE).select_related(
        "from_organization", "to_organization", "port_call", "port_call__vessel", "port_call__port"
    )
    incoming = base.filter(status=RequestStatus.PENDING).order_by("created_at")
    jobs = []
    for r in base.filter(status=RequestStatus.ACCEPTED).exclude(port_call__status__in=ACTIVE_EXCLUDE).order_by("-responded_at")[:50]:
        thread = ChatThread.objects.filter(request=r).first()
        jobs.append({"request": request_row(r), "port_call": pc_row(r.port_call, restricted=True), "chat_thread_id": thread.pk if thread else None})
    invoices = VendorInvoice.objects.filter(vendor_organization_id=org_id)
    by_status = dict(invoices.values_list("status").annotate(c=Count("id")).values_list("status", "c"))
    unpaid = invoices.filter(status__in=[InvoiceStatus.ISSUED, InvoiceStatus.ACCEPTED])
    unpaid_totals = {row["currency_id"]: str(row["s"]) for row in unpaid.values("currency_id").annotate(s=Sum("total_amount"))}
    payments = Payment.objects.filter(payee_organization_id=org_id, kind=PaymentKind.VENDOR_PAYMENT).select_related(
        "payer_organization", "payee_organization", "port_call", "recorded_by_user", "confirmed_by_user"
    ).order_by("-paid_at")[:10]
    return {
        "incoming_requests": [request_row(r) for r in incoming],
        "active_jobs": jobs,
        "invoices_by_status": by_status,
        "unpaid_total": [{"amount": amt, "currency_code": cur} for cur, amt in unpaid_totals.items()],
        "recent_payments": [payment_data(p) for p in payments],
    }


class DashboardView(APIView):
    permission_classes = approved(Role.OWNER, Role.AGENT, Role.MERCHANT)

    def get(self, request):
        role = request.user.role
        if role == Role.AGENT:
            return Response({"role": role, **agent_dashboard(request.user)})
        if role == Role.OWNER:
            return Response({"role": role, **owner_dashboard(request.user)})
        if role == Role.MERCHANT:
            return Response({"role": role, **merchant_dashboard(request.user)})
        raise NotFound()
