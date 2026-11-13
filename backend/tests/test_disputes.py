"""Dispute rules (STATE_MACHINES.md §8, §10)."""
from decimal import Decimal

import pytest

from apps.core.enums import AccountKind
from apps.core.exceptions import InvalidTransition, ValidationFailed
from apps.disbursements import services as da
from apps.disputes import services as disp


def _issued(world):
    out = world.stage("FDA_ISSUED")
    out["line"] = out["fda"].line_items.get(vendor_invoice=out["invoice"])
    out["fee_line"] = out["fda"].line_items.get(service_category__code="AGENCY_FEE")
    return out


@pytest.mark.django_db
def test_finalize_blocked_while_dispute_open(world):
    out = _issued(world)
    d = disp.open_dispute(actor=world.owner, line_item_id=out["line"].pk, reason="Too high")
    out["pc"].refresh_from_db()
    assert out["pc"].status == "DISPUTED"
    with pytest.raises(InvalidTransition) as exc:
        da.finalize_fda(actor=world.agent, account=out["fda"])
    assert exc.value.error_code == "open_disputes"
    disp.resolve(actor=world.agent, dispute=d, resolution_type="EXPLAINED", note="Tariff attached")
    out["pc"].refresh_from_db()
    assert out["pc"].status == "FDA_ISSUED"
    da.finalize_fda(actor=world.agent, account=out["fda"])


@pytest.mark.django_db
def test_one_live_dispute_per_line(world):
    out = _issued(world)
    disp.open_dispute(actor=world.owner, line_item_id=out["line"].pk, reason="A")
    with pytest.raises(InvalidTransition):
        disp.open_dispute(actor=world.owner, line_item_id=out["line"].pk, reason="B")
    disp.open_dispute(actor=world.owner, line_item_id=out["fee_line"].pk, reason="C")  # another line is fine


@pytest.mark.django_db
def test_only_owner_opens_and_only_on_current_issued_fda(world):
    out = _issued(world)
    with pytest.raises(ValidationFailed):
        disp.open_dispute(actor=world.owner2, line_item_id=out["line"].pk, reason="not mine")
    pda_line = out["pda"].line_items.first()
    with pytest.raises(InvalidTransition):
        disp.open_dispute(actor=world.owner, line_item_id=pda_line.pk, reason="PDA line")


@pytest.mark.django_db
def test_adjusted_credit_line_on_invoice_backed_line(world):
    out = _issued(world)
    d = disp.open_dispute(actor=world.owner, line_item_id=out["line"].pk, reason="Agreed 80k")
    d = disp.resolve(actor=world.agent, dispute=d, resolution_type="ADJUSTED", note="Credit", adjusted_local_amount="80000.00")
    draft = da.current_account(out["pc"], AccountKind.FDA)
    assert draft.version == 2 and draft.status == "DRAFT"
    out["fda"].refresh_from_db()
    assert out["fda"].status == "SUPERSEDED"
    credit = draft.line_items.get(is_adjustment=True)
    assert credit.local_amount == Decimal("-10000.00") and credit.amount == Decimal("-120.00") and credit.source_dispute_id == d.pk
    assert d.resolved_in_account_id == draft.pk and d.adjustment_line_item_id == credit.pk
    assert draft.total_amount == Decimal("1960.00")  # 1080 + 1000 − 120
    da.issue(actor=world.agent, account=draft)
    _, settlement = da.finalize_fda(actor=world.agent, account=draft)
    assert settlement.fda_total == Decimal("1960.00")


@pytest.mark.django_db
def test_edit_line_mode_for_agent_paid_line(world):
    out = _issued(world)
    d = disp.open_dispute(actor=world.owner, line_item_id=out["fee_line"].pk, reason="Fee was agreed at 900")
    with pytest.raises(ValidationFailed):
        disp.resolve(actor=world.agent, dispute=out_line_dispute(world, out), resolution_type="ADJUSTED", note="x",
                     adjusted_local_amount="1.00", mode="EDIT_LINE")
    disp.resolve(actor=world.agent, dispute=d, resolution_type="ADJUSTED", note="Agreed", adjusted_local_amount="900.00", mode="EDIT_LINE")
    draft = da.current_account(out["pc"], AccountKind.FDA)
    fee = draft.line_items.get(service_category__code="AGENCY_FEE")
    assert fee.amount == Decimal("900.00") and fee.supersedes_line_item_id == out["fee_line"].pk


def out_line_dispute(world, out):
    return disp.open_dispute(actor=world.owner, line_item_id=out["line"].pk, reason="Invoice line")


@pytest.mark.django_db
def test_reject_reopen_once(world):
    out = _issued(world)
    d = disp.open_dispute(actor=world.owner, line_item_id=out["line"].pk, reason="Why?")
    disp.reject(actor=world.agent, dispute=d, note="Per tariff")
    d = disp.reopen(actor=world.owner, dispute=d, body="Tariff is outdated")
    assert d.status == "OPEN" and d.reopen_count == 1
    disp.reject(actor=world.agent, dispute=d, note="Still per tariff")
    with pytest.raises(InvalidTransition):
        disp.reopen(actor=world.owner, dispute=d)
    assert [e.event_type for e in d.events.all()] == ["OPENED", "STATUS_CHANGED", "REOPENED", "STATUS_CHANGED"]


@pytest.mark.django_db
def test_withdraw_and_comment_permissions(world):
    from apps.core.exceptions import Forbidden

    out = _issued(world)
    d = disp.open_dispute(actor=world.owner, line_item_id=out["line"].pk, reason="Hmm")
    disp.comment(actor=world.agent, dispute=d, body="Looking")
    with pytest.raises(Forbidden):
        disp.comment(actor=world.agent2, dispute=d, body="intruder")
    with pytest.raises(Forbidden):
        disp.withdraw(actor=world.agent, dispute=d)
    disp.withdraw(actor=world.owner, dispute=d)
    out["pc"].refresh_from_db()
    assert out["pc"].status == "FDA_ISSUED"
    with pytest.raises(InvalidTransition):
        disp.comment(actor=world.owner, dispute=d, body="late")


@pytest.mark.django_db
def test_discard_restores_previous_version_unless_it_carries_adjustments(world):
    out = _issued(world)
    draft = da.revise(actor=world.agent, account=out["fda"])
    restored = da.discard(actor=world.agent, account=draft)
    assert restored.pk == out["fda"].pk and restored.status == "ISSUED" and restored.is_current
    d = disp.open_dispute(actor=world.owner, line_item_id=out["line"].pk, reason="x")
    disp.resolve(actor=world.agent, dispute=d, resolution_type="ADJUSTED", note="credit", adjusted_local_amount="1.00")
    with pytest.raises(InvalidTransition):
        da.discard(actor=world.agent, account=da.current_account(out["pc"], AccountKind.FDA))


@pytest.mark.django_db
def test_dispute_open_after_revision_tracks_descendant_line(world):
    out = _issued(world)
    d1 = disp.open_dispute(actor=world.owner, line_item_id=out["fee_line"].pk, reason="fee")
    d2 = disp.open_dispute(actor=world.owner, line_item_id=out["line"].pk, reason="pilot")
    disp.resolve(actor=world.agent, dispute=d1, resolution_type="ADJUSTED", note="ok", adjusted_local_amount="950.00")
    out["pc"].refresh_from_db()
    assert out["pc"].status == "DISPUTED"  # d2 still live
    # d2's line lives in v1; resolving it adjusts the descendant line in the existing v2 draft.
    disp.resolve(actor=world.agent, dispute=d2, resolution_type="ADJUSTED", note="ok", adjusted_local_amount="85000.00")
    draft = da.current_account(out["pc"], AccountKind.FDA)
    assert draft.version == 2
    assert draft.total_amount == Decimal("950.00") + Decimal("1080.00") - Decimal("60.00")
    da.issue(actor=world.agent, account=draft)
    out["pc"].refresh_from_db()
    assert out["pc"].status == "FDA_ISSUED"
