from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.enums import PaymentKind, PaymentMethod, Role
from apps.core.exceptions import NotFound
from apps.core.permissions import approved
from apps.core.serializers import MoneyField, OptionalReasonSerializer, RequiredNoteSerializer, dec, dt, money, org_summary, user_summary, validated
from apps.disbursements.views import pdf_response
from apps.portcalls.selectors import get_port_call_for, party_role, port_calls_for

from . import services
from .models import Payment, Settlement


class PaymentInputSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=[PaymentKind.ADVANCE, PaymentKind.BALANCE, PaymentKind.REFUND])
    amount = MoneyField(min_value=0)
    currency_code = serializers.CharField(max_length=3, required=False)
    fx_rate_id = serializers.IntegerField(required=False, allow_null=True)
    paid_at = serializers.DateTimeField()
    method = serializers.ChoiceField(choices=PaymentMethod.choices, required=False)
    bank_reference = serializers.CharField(required=False, allow_blank=True)
    provider = serializers.CharField(required=False, default="MANUAL")


def payment_data(p):
    return {
        "id": p.pk,
        "reference": p.reference,
        "port_call_id": p.port_call_id,
        "kind": p.kind,
        "status": p.status,
        "payer": org_summary(p.payer_organization),
        "payee": org_summary(p.payee_organization),
        "amount": money(p.amount, p.currency_id),
        "fx_rate_id": p.fx_rate_id,
        "fx_rate_applied": dec(p.fx_rate_applied),
        "settlement_amount": money(p.settlement_amount, p.port_call.settlement_currency_id),
        "disbursement_account_id": p.disbursement_account_id,
        "settlement_id": p.settlement_id,
        "vendor_invoice_id": p.vendor_invoice_id,
        "method": p.method,
        "bank_reference": p.bank_reference,
        "provider": p.provider,
        "provider_reference": p.provider_reference,
        "paid_at": dt(p.paid_at),
        "recorded_by": user_summary(p.recorded_by_user),
        "confirmed_by": user_summary(p.confirmed_by_user),
        "confirmed_at": dt(p.confirmed_at),
        "cancelled_reason": p.cancelled_reason,
        "created_at": dt(p.created_at),
    }


def settlement_data(s):
    payments = s.payments.select_related("payer_organization", "payee_organization", "port_call", "recorded_by_user", "confirmed_by_user").order_by("paid_at")
    return {
        "id": s.pk,
        "reference": s.reference,
        "port_call_id": s.port_call_id,
        "fda_id": s.fda_id,
        "pda_id": s.pda_id,
        "currency_code": s.currency_id,
        "direction": s.direction,
        "status": s.status,
        "pda_total": money(s.pda_total, s.currency_id),
        "fda_total": money(s.fda_total, s.currency_id),
        "advance_total": money(s.advance_total, s.currency_id),
        "balance": money(s.balance, s.currency_id),
        "paid": money(services.paid_against(s), s.currency_id),
        "outstanding": money(services.outstanding(s), s.currency_id),
        "payments": [payment_data(p) for p in payments],
        "closed_at": dt(s.closed_at),
        "closed_by": user_summary(s.closed_by_user),
        "created_at": dt(s.created_at),
    }


def _payments_qs():
    return Payment.objects.select_related("payer_organization", "payee_organization", "port_call", "recorded_by_user", "confirmed_by_user")


def get_payment(user, pk):
    p = _payments_qs().filter(pk=pk).first()
    if p is None:
        raise NotFound()
    if user.role == Role.ADMIN:
        return p
    org_id = user.organization_id
    if org_id not in (p.payer_organization_id, p.payee_organization_id):
        if not (user.role == Role.OWNER and p.port_call.owner_organization_id == org_id and p.kind != PaymentKind.VENDOR_PAYMENT):
            raise NotFound()
    return p


class PortCallPaymentsView(APIView):
    permission_classes = approved(Role.OWNER, Role.AGENT, Role.MERCHANT, Role.ADMIN)

    def get(self, request, pk):
        pc = get_port_call_for(request.user, pk)
        qs = _payments_qs().filter(port_call=pc)
        role = party_role(request.user, pc)
        if role == "MERCHANT":
            qs = qs.filter(kind=PaymentKind.VENDOR_PAYMENT, payee_organization_id=request.user.organization_id)
        elif role == "OWNER":
            qs = qs.exclude(kind=PaymentKind.VENDOR_PAYMENT)
        for key in ("kind", "status"):
            if request.query_params.get(key):
                qs = qs.filter(**{key: request.query_params[key]})
        return Response([payment_data(p) for p in qs.order_by("-paid_at", "-id")])

    def post(self, request, pk):
        if request.user.role not in (Role.OWNER, Role.AGENT):
            raise NotFound()
        data = validated(PaymentInputSerializer, request.data)
        pc = get_port_call_for(request.user, pk)
        payment = services.record_payment(actor=request.user, port_call=pc, data=dict(data))
        return Response(payment_data(get_payment(request.user, payment.pk)), status=status.HTTP_201_CREATED)


class PaymentDetailView(APIView):
    permission_classes = approved(Role.OWNER, Role.AGENT, Role.MERCHANT, Role.ADMIN)

    def get(self, request, pk):
        return Response(payment_data(get_payment(request.user, pk)))


class PaymentConfirmView(APIView):
    permission_classes = approved(Role.OWNER, Role.AGENT, Role.ADMIN)

    def post(self, request, pk):
        services.confirm_payment(actor=request.user, payment=get_payment(request.user, pk))
        return Response(payment_data(get_payment(request.user, pk)))


class PaymentCancelView(APIView):
    permission_classes = approved(Role.OWNER, Role.AGENT, Role.ADMIN)

    def post(self, request, pk):
        data = validated(OptionalReasonSerializer, request.data)
        services.cancel_payment(actor=request.user, payment=get_payment(request.user, pk), reason=data["reason"])
        return Response(payment_data(get_payment(request.user, pk)))


def get_settlement(user, pk):
    s = Settlement.objects.select_related("port_call").filter(pk=pk).first()
    if s is None or not port_calls_for(user).filter(pk=s.port_call_id).exists() or party_role(user, s.port_call) == "MERCHANT":
        raise NotFound()
    return s


class PortCallSettlementView(APIView):
    permission_classes = approved(Role.OWNER, Role.AGENT, Role.ADMIN)

    def get(self, request, pk):
        pc = get_port_call_for(request.user, pk)
        s = Settlement.objects.filter(port_call=pc).first()
        if s is None:
            raise NotFound("The FDA has not been finalized yet.")
        return Response(settlement_data(s))


class SettlementForceCloseView(APIView):
    permission_classes = approved(Role.AGENT)

    def post(self, request, pk):
        data = validated(RequiredNoteSerializer, request.data)
        s = services.force_close_settlement(actor=request.user, settlement=get_settlement(request.user, pk), note=data["note"])
        s.refresh_from_db()
        return Response(settlement_data(s))


class SettlementPdfView(APIView):
    permission_classes = approved(Role.OWNER, Role.AGENT, Role.ADMIN)

    def get(self, request, pk):
        from apps.documents.pdf import settlement_pdf

        s = get_settlement(request.user, pk)
        doc, data = settlement_pdf(s, user=request.user)
        return pdf_response(request, doc, data, f"{s.reference}-preview.pdf")
