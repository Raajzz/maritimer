"""Settlement math (ARCHITECTURE.md §3.4, STATE_MACHINES.md §7)."""
from decimal import Decimal

import pytest

from apps.core.enums import AccountKind
from apps.core.exceptions import InvalidTransition, ValidationFailed
from apps.disbursements import services as da
from apps.payments import services as pay
from apps.payments.services import compute_balance


def test_compute_balance_directions():
    assert compute_balance(Decimal("100.00"), Decimal("80.00")) == (Decimal("20.00"), "BALANCE_DUE")
    assert compute_balance(Decimal("80.00"), Decimal("100.00")) == (Decimal("-20.00"), "REFUND_DUE")
    assert compute_balance(Decimal("80.00"), Decimal("80.00")) == (Decimal("0.00"), "NIL")


def _finalize(world, advance, invoice_amount="90000.00"):
    out = world.stage("FDA_FINAL", advance=advance, invoice_amount=invoice_amount)
    out["pc"].refresh_from_db()
    return out


@pytest.mark.django_db
def test_balance_due_partial_then_full_payment_closes_and_settles(world):
    # FDA = 1080.00 (invoice) + 1000.00 (agency fee) = 2080.00; advance 1500 → balance due 580.00
    out = _finalize(world, advance="1500.00")
    s = out["settlement"]
    assert (s.fda_total, s.advance_total, s.balance, s.direction) == (Decimal("2080.00"), Decimal("1500.00"), Decimal("580.00"), "BALANCE_DUE")
    pc = out["pc"]
    p1 = pay.record_payment(actor=world.owner, port_call=pc, data={"kind": "BALANCE", "amount": "300.00", "paid_at": world.now})
    pay.confirm_payment(actor=world.agent, payment=p1)
    s.refresh_from_db()
    assert s.status == "PARTIALLY_PAID" and pay.outstanding(s) == Decimal("280.00")
    with pytest.raises(ValidationFailed):  # over-payment rejected
        pay.record_payment(actor=world.owner, port_call=pc, data={"kind": "BALANCE", "amount": "280.01", "paid_at": world.now})
    p2 = pay.record_payment(actor=world.owner, port_call=pc, data={"kind": "BALANCE", "amount": "280.00", "paid_at": world.now})
    pay.confirm_payment(actor=world.agent, payment=p2)
    s.refresh_from_db(); pc.refresh_from_db()
    assert s.status == "CLOSED" and pc.status == "SETTLED"


@pytest.mark.django_db
def test_refund_due_is_paid_by_agent_and_confirmed_by_owner(world):
    out = _finalize(world, advance="2500.00")
    s = out["settlement"]
    assert s.direction == "REFUND_DUE" and s.balance == Decimal("-420.00")
    with pytest.raises(ValidationFailed):  # wrong kind for this direction
        pay.record_payment(actor=world.owner, port_call=out["pc"], data={"kind": "BALANCE", "amount": "1.00", "paid_at": world.now})
    p = pay.record_payment(actor=world.agent, port_call=out["pc"], data={"kind": "REFUND", "amount": "420.00", "paid_at": world.now})
    from apps.core.exceptions import Forbidden

    with pytest.raises(Forbidden):  # payer cannot confirm its own payment
        pay.confirm_payment(actor=world.agent, payment=p)
    pay.confirm_payment(actor=world.owner, payment=p)
    s.refresh_from_db()
    assert s.status == "CLOSED"


@pytest.mark.django_db
def test_nil_balance_closes_immediately(world):
    out = _finalize(world, advance="2080.00")
    s = out["settlement"]
    out["pc"].refresh_from_db()
    assert s.direction == "NIL" and s.status == "CLOSED" and out["pc"].status == "SETTLED"


@pytest.mark.django_db
def test_only_confirmed_advances_count(world):
    out = world.stage("PDA_APPROVED")
    pc = out["pc"]
    pending = pay.record_payment(actor=world.owner, port_call=pc, data={"kind": "ADVANCE", "amount": "999.00", "paid_at": world.now})
    assert pay.advance_total(pc) == Decimal("0.00")
    pay.confirm_payment(actor=world.agent, payment=pending)
    pc.refresh_from_db()
    assert pay.advance_total(pc) == Decimal("999.00") and pc.status == "ADVANCE_RECEIVED"


@pytest.mark.django_db
def test_advance_in_other_currency_converts_to_usd(world):
    out = world.stage("PDA_APPROVED")
    p = pay.record_payment(actor=world.owner, port_call=out["pc"], data={"kind": "ADVANCE", "amount": "100000.00", "currency_code": "INR", "paid_at": world.now})
    assert p.settlement_amount == Decimal("1200.00") and p.fx_rate_id == world.rate_old.pk


@pytest.mark.django_db
def test_advance_requires_approved_pda(world):
    out = world.stage("PDA_SENT")
    with pytest.raises(InvalidTransition):
        pay.record_payment(actor=world.owner, port_call=out["pc"], data={"kind": "ADVANCE", "amount": "10.00", "paid_at": world.now})


@pytest.mark.django_db
def test_force_close_respects_tolerance(world, settings):
    out = _finalize(world, advance="2079.50")  # balance due 0.50
    s = out["settlement"]
    with pytest.raises(InvalidTransition):
        pay.force_close_settlement(actor=world.agent, settlement=s, note="write-off")
    settings.SETTLEMENT_WRITEOFF_TOLERANCE = "1.00"
    pay.force_close_settlement(actor=world.agent, settlement=s, note="bank charges write-off")
    s.refresh_from_db()
    assert s.status == "CLOSED"


@pytest.mark.django_db
def test_settlement_snapshot_is_immutable_and_unique(world):
    out = _finalize(world, advance="1500.00")
    with pytest.raises(InvalidTransition):
        da.finalize_fda(actor=world.agent, account=da.current_account(out["pc"], AccountKind.FDA))
