"""Payments and settlement (STATE_MACHINES.md §6–7, ARCHITECTURE.md §3.4).

Payment provider abstraction: `PROVIDERS[name].record(payment)` is called when a payment is recorded.
v1 ships only MANUAL (bank transfers recorded by hand). A gateway adds a provider class here and
fills provider_reference / provider_payload; nothing else changes.
"""
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.audit import audit
from apps.core.enums import (
    AccountKind,
    AccountStatus,
    PaymentKind,
    PaymentMethod,
    PaymentStatus,
    PortCallStatus,
    Role,
    SettlementDirection,
    SettlementStatus,
)
from apps.core.exceptions import Forbidden, InvalidTransition, ValidationFailed
from apps.core.money import convert, round_money, to_decimal
from apps.core.references import next_reference
from apps.core.services import lock, require, transition
from apps.masterdata.services import resolve_rate
from apps.portcalls.services import lock_port_call, set_status

from .models import Payment, Settlement
from .transitions import PAYMENT_MACHINE, SETTLEMENT_MACHINE


class ManualProvider:
    name = "MANUAL"

    def record(self, payment):
        return payment


PROVIDERS = {"MANUAL": ManualProvider()}

ADVANCE_STATES = {PortCallStatus.PDA_APPROVED, PortCallStatus.ADVANCE_RECEIVED, PortCallStatus.IN_PORT, PortCallStatus.DEPARTED}
SETTLEMENT_PAYABLE = {SettlementStatus.OPEN, SettlementStatus.PARTIALLY_PAID}


# ---- Settlement math -------------------------------------------------------------


def advance_total(port_call) -> Decimal:
    total = Payment.objects.filter(port_call=port_call, kind=PaymentKind.ADVANCE, status=PaymentStatus.CONFIRMED).aggregate(s=Sum("settlement_amount"))["s"]
    return round_money(total or Decimal("0"), port_call.settlement_currency_id)


def compute_balance(fda_total, advance) -> tuple[Decimal, str]:
    balance = to_decimal(fda_total) - to_decimal(advance)
    if balance > 0:
        return balance, SettlementDirection.BALANCE_DUE
    if balance < 0:
        return balance, SettlementDirection.REFUND_DUE
    return balance, SettlementDirection.NIL


def paid_against(settlement) -> Decimal:
    total = settlement.payments.filter(kind__in=[PaymentKind.BALANCE, PaymentKind.REFUND], status=PaymentStatus.CONFIRMED).aggregate(s=Sum("settlement_amount"))["s"]
    return round_money(total or Decimal("0"), settlement.currency_id)


def outstanding(settlement) -> Decimal:
    return round_money(abs(settlement.balance) - paid_against(settlement), settlement.currency_id)


def create_settlement(*, actor, port_call, fda):
    """Called only by fda.finalize inside its transaction. Snapshot is immutable (SCHEMA.md D10)."""
    from apps.disbursements.services import reference_pda

    pda = reference_pda(port_call)
    advance = advance_total(port_call)
    balance, direction = compute_balance(fda.total_amount, advance)
    settlement = Settlement.objects.create(
        reference=next_reference("SET"),
        port_call=port_call,
        fda=fda,
        pda=pda if pda and pda.status == AccountStatus.APPROVED else None,
        currency_id=port_call.settlement_currency_id,
        pda_total=pda.total_amount if pda else Decimal("0.00"),
        fda_total=fda.total_amount,
        advance_total=advance,
        balance=balance,
        direction=direction,
    )
    audit(actor=actor, action="settlement.created", entity=settlement, port_call=port_call, to_state=settlement.status,
          metadata={"fda_total": fda.total_amount, "advance_total": advance, "balance": balance, "direction": direction})
    if direction == SettlementDirection.NIL:
        _close_settlement(actor=actor, settlement=settlement, port_call=port_call, event="paid_in_full", note="Nil balance")
    return settlement


def _close_settlement(*, actor, settlement, port_call, event, note=None):
    transition(machine=SETTLEMENT_MACHINE, instance=settlement, event=event, actor=actor, action="settlement.closed", port_call=port_call,
               metadata={"note": note, "outstanding": outstanding(settlement)},
               extra_updates={"closed_at": timezone.now(), "closed_by_user": actor})
    set_status(port_call=port_call, event="settle", actor=actor, action="port_call.settled")


def _refresh_settlement(*, actor, settlement, port_call):
    remaining = outstanding(settlement)
    if remaining == 0:
        _close_settlement(actor=actor, settlement=settlement, port_call=port_call, event="paid_in_full")
    elif settlement.status == SettlementStatus.OPEN and paid_against(settlement) > 0:
        transition(machine=SETTLEMENT_MACHINE, instance=settlement, event="partial_payment", actor=actor,
                   action="settlement.partially_paid", port_call=port_call, metadata={"outstanding": remaining})


# ---- Payments -----------------------------------------------------------------------


def _parties(port_call, kind, vendor_invoice=None):
    if kind in (PaymentKind.ADVANCE, PaymentKind.BALANCE):
        return port_call.owner_organization_id, port_call.agent_organization_id
    if kind == PaymentKind.REFUND:
        return port_call.agent_organization_id, port_call.owner_organization_id
    return port_call.agent_organization_id, vendor_invoice.vendor_organization_id


RECORDER_ROLE = {
    PaymentKind.ADVANCE: "OWNER",
    PaymentKind.BALANCE: "OWNER",
    PaymentKind.REFUND: "AGENT",
    PaymentKind.VENDOR_PAYMENT: "AGENT",
}


@transaction.atomic
def record_payment(*, actor, port_call, data, vendor_invoice=None, auto_confirm=False):
    port_call = lock_port_call(port_call)
    kind = data.get("kind")
    require(kind in PaymentKind.values, "Invalid payment kind.", {"kind": ["Invalid choice."]})
    payer_id, payee_id = _parties(port_call, kind, vendor_invoice)
    if actor.organization_id != payer_id:
        raise Forbidden(f"Only the payer ({RECORDER_ROLE[kind].lower()}) records a {kind} payment.")

    amount = to_decimal(data.get("amount", "0"))
    currency = data.get("currency_code") or port_call.settlement_currency_id
    require(amount > 0, "Amount must be positive.", {"amount": ["Must be > 0."]})
    amount = round_money(amount, currency)
    paid_at = data.get("paid_at") or timezone.now()
    applied = resolve_rate(currency, port_call.settlement_currency_id, rate_id=data.get("fx_rate_id"), as_of=paid_at)
    settlement_amount = convert(amount, applied.applied, port_call.settlement_currency_id)

    links = {}
    if kind == PaymentKind.ADVANCE:
        if port_call.status not in ADVANCE_STATES:
            raise InvalidTransition(f"Advances can be recorded after PDA approval and before the FDA (port call is {port_call.status}).")
        from apps.disbursements.services import current_account

        pda = current_account(port_call, AccountKind.PDA)
        require(pda is not None and pda.status == AccountStatus.APPROVED, "The current PDA must be approved before recording an advance.")
        links["disbursement_account"] = pda
    elif kind in (PaymentKind.BALANCE, PaymentKind.REFUND):
        settlement = Settlement.objects.select_for_update().filter(port_call=port_call).first()
        require(settlement is not None, "No settlement exists yet; the FDA must be finalized first.")
        expected = SettlementDirection.BALANCE_DUE if kind == PaymentKind.BALANCE else SettlementDirection.REFUND_DUE
        require(settlement.direction == expected, f"This settlement is {settlement.direction}; a {kind} payment does not apply.")
        if settlement.status not in SETTLEMENT_PAYABLE:
            raise InvalidTransition("This settlement is already closed.")
        remaining = outstanding(settlement)
        require(settlement_amount <= remaining, "Payment exceeds the outstanding amount.",
                {"amount": [f"Outstanding is {remaining} {settlement.currency_id}."]})
        links["settlement"] = settlement
    else:
        require(vendor_invoice is not None, "Vendor payments need an invoice.")
        links["vendor_invoice"] = vendor_invoice

    method = data.get("method") or PaymentMethod.BANK_TRANSFER
    require(method in PaymentMethod.values, "Invalid payment method.", {"method": ["Invalid choice."]})
    provider_name = data.get("provider") or "MANUAL"
    require(provider_name in PROVIDERS, "Unknown payment provider.", {"provider": ["Only MANUAL is supported."]})
    payment = Payment.objects.create(
        reference=next_reference("PAY"),
        port_call=port_call,
        kind=kind,
        payer_organization_id=payer_id,
        payee_organization_id=payee_id,
        amount=amount,
        currency_id=currency,
        fx_rate=applied.fx_rate,
        fx_rate_applied=applied.applied,
        settlement_amount=settlement_amount,
        method=method,
        bank_reference=data.get("bank_reference") or "",
        provider=provider_name,
        paid_at=paid_at,
        recorded_by_user=actor,
        **links,
    )
    PROVIDERS[provider_name].record(payment)
    audit(actor=actor, action="payment.recorded", entity=payment, port_call=port_call, to_state=payment.status,
          metadata={"kind": kind, "amount": amount, "currency": currency, "settlement_amount": settlement_amount, "fx": applied.note})
    if auto_confirm:
        _confirm(actor=actor, payment=payment, port_call=port_call)
    return payment


def _confirm(*, actor, payment, port_call):
    if payment.kind == PaymentKind.ADVANCE and port_call.status not in ADVANCE_STATES:
        raise InvalidTransition(f"The port call is {port_call.status}; this advance can no longer be confirmed. Cancel it instead.")
    settlement = None
    if payment.kind in (PaymentKind.BALANCE, PaymentKind.REFUND):
        settlement = Settlement.objects.select_for_update().get(pk=payment.settlement_id)
        if settlement.status not in SETTLEMENT_PAYABLE:
            raise InvalidTransition("This settlement is already closed.")
        remaining = outstanding(settlement)
        if payment.settlement_amount > remaining:
            raise ValidationFailed("Payment exceeds the outstanding amount.", {"amount": [f"Outstanding is {remaining}."]})
    transition(machine=PAYMENT_MACHINE, instance=payment, event="confirm", actor=actor, action="payment.confirmed", port_call=port_call,
               metadata={"kind": payment.kind, "settlement_amount": payment.settlement_amount},
               extra_updates={"confirmed_by_user": actor, "confirmed_at": timezone.now()})
    if payment.kind == PaymentKind.ADVANCE and port_call.status == PortCallStatus.PDA_APPROVED:
        set_status(port_call=port_call, event="advance_received", actor=actor, action="port_call.advance_received",
                   metadata={"payment": payment.reference})
    elif settlement is not None:
        _refresh_settlement(actor=actor, settlement=settlement, port_call=port_call)
    elif payment.kind == PaymentKind.VENDOR_PAYMENT:
        from apps.invoices.services import mark_invoice_paid

        mark_invoice_paid(actor=actor, invoice=payment.vendor_invoice, port_call=port_call)
    return payment


@transaction.atomic
def confirm_payment(*, actor, payment):
    port_call = lock_port_call(payment.port_call)
    payment = lock(payment)
    if actor.role != Role.ADMIN and actor.organization_id != payment.payee_organization_id:
        raise Forbidden("Only the receiving party confirms a payment.")
    return _confirm(actor=actor, payment=payment, port_call=port_call)


@transaction.atomic
def cancel_payment(*, actor, payment, reason=""):
    port_call = lock_port_call(payment.port_call)
    payment = lock(payment)
    is_payer = actor.organization_id == payment.payer_organization_id
    is_payee = actor.organization_id == payment.payee_organization_id
    if actor.role != Role.ADMIN and not (is_payer or is_payee):
        raise Forbidden()
    if is_payee and not is_payer and actor.role != Role.ADMIN:
        require(reason, "A reason is required when the payee cancels.", {"reason": ["Required."]})
    return transition(machine=PAYMENT_MACHINE, instance=payment, event="cancel", actor=actor, action="payment.cancelled",
                      port_call=port_call, metadata={"reason": reason}, extra_updates={"cancelled_reason": reason or None})


@transaction.atomic
def force_close_settlement(*, actor, settlement, note):
    require(note, "A note is required.", {"note": ["Required."]})
    port_call = lock_port_call(settlement.port_call)
    settlement = lock(settlement)
    if actor.organization_id != port_call.agent_organization_id:
        raise Forbidden("Only the agent can force-close a settlement.")
    tolerance = to_decimal(getattr(settings, "SETTLEMENT_WRITEOFF_TOLERANCE", "0.00"))
    remaining = outstanding(settlement)
    if remaining > tolerance:
        raise InvalidTransition(f"Outstanding {remaining} exceeds the write-off tolerance {tolerance}.")
    _close_settlement(actor=actor, settlement=settlement, port_call=port_call, event="force_close", note=note)
    return settlement
