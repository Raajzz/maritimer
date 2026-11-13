from datetime import timedelta
from decimal import Decimal

import pytest

from apps.core.exceptions import ValidationFailed
from apps.core.money import convert, invert_rate, round_money, sum_money, to_decimal
from apps.masterdata.services import record_fx_rate, resolve_rate, select_rate


def test_floats_are_rejected():
    with pytest.raises(TypeError):
        to_decimal(0.1)


@pytest.mark.django_db
def test_round_half_up_to_minor_units(world):
    assert round_money("2.345", "USD") == Decimal("2.35")
    assert round_money("2.344", "USD") == Decimal("2.34")
    assert round_money("-2.345", "USD") == Decimal("-2.35")


@pytest.mark.django_db
def test_convert_rounds_once_per_line(world):
    # 202,960 INR × 0.01201 = 2437.5496 → 2437.55
    assert convert("202960.00", "0.0120100000", "USD") == Decimal("2437.55")
    lines = [convert(a, "0.012", "USD") for a in ("100.40", "100.40", "100.40")]  # 1.2048 each → 1.20
    assert sum_money(lines, "USD") == Decimal("3.60")  # sum of rounded lines, not round(sum)


def test_invert_rate_has_ten_places():
    assert invert_rate("83.3333333333") == Decimal("0.0120000000")


@pytest.mark.django_db
def test_select_latest_rate_on_or_before_as_of(world):
    applied = select_rate("INR", "USD", world.now)
    assert applied.fx_rate == world.rate_old  # rate_new is dated in the future
    assert applied.applied == Decimal("0.0120000000")
    later = select_rate("INR", "USD", world.now + timedelta(days=31))
    assert later.fx_rate == world.rate_new


@pytest.mark.django_db
def test_inverse_rate_fallback(world):
    rate = record_fx_rate(actor=world.admin, base_currency_code="USD", quote_currency_code="SGD", rate="1.3400000000",
                          as_of=world.now - timedelta(days=1))
    applied = select_rate("SGD", "USD", world.now)
    assert applied.fx_rate == rate and applied.inverse
    assert applied.applied == Decimal("0.7462686567")


@pytest.mark.django_db
def test_missing_rate_raises(world):
    with pytest.raises(ValidationFailed) as exc:
        select_rate("AED", "USD", world.now)
    assert exc.value.error_code == "fx_rate_missing"


@pytest.mark.django_db
def test_same_currency_is_identity_and_rejects_rate(world):
    assert resolve_rate("USD", "USD").applied == Decimal("1")
    with pytest.raises(ValidationFailed):
        resolve_rate("USD", "USD", rate_id=world.rate_old.pk)


@pytest.mark.django_db
def test_rate_by_id_must_match_pair(world):
    with pytest.raises(ValidationFailed):
        resolve_rate("SGD", "USD", rate_id=world.rate_old.pk)


@pytest.mark.django_db
def test_fx_rates_are_append_only(world):
    world.rate_old.rate = Decimal("1")
    with pytest.raises(RuntimeError):
        world.rate_old.save()


@pytest.mark.django_db
def test_pda_line_amount_is_server_computed_and_stores_applied_rate(world):
    from apps.disbursements import services as da

    pc = world.port_call()
    pda = da.create_pda(actor=world.agent, port_call=pc, line_items=world.pda_lines())
    lines = {l.service_category.code: l for l in pda.line_items.select_related("service_category")}
    assert lines["PILOTAGE"].amount == Decimal("1200.00")
    assert lines["PILOTAGE"].fx_rate_id == world.rate_old.pk
    assert lines["PILOTAGE"].fx_rate_applied == Decimal("0.0120000000")
    assert lines["AGENCY_FEE"].fx_rate_id is None and lines["AGENCY_FEE"].fx_rate_applied == 1
    pda.refresh_from_db()
    assert pda.total_amount == Decimal("1200.00") + Decimal("2400.00") + Decimal("1000.00")


@pytest.mark.django_db
def test_client_amount_mismatch_rejected(world):
    from apps.disbursements import services as da

    pc = world.port_call()
    lines = world.pda_lines()
    lines[0]["amount"] = "1199.99"
    with pytest.raises(ValidationFailed):
        da.create_pda(actor=world.agent, port_call=pc, line_items=lines)


@pytest.mark.django_db
def test_fda_uses_rate_as_of_atd_and_is_reproducible(world):
    from apps.disbursements.services import variance

    out = world.stage("FDA_ISSUED", invoice_amount="90000.00")
    fda = out["fda"]
    line = fda.line_items.get(vendor_invoice=out["invoice"])
    assert line.fx_rate_id == world.rate_old.pk
    assert line.amount == Decimal("1080.00")
    # A newer rate recorded later must not change the stored FDA figures.
    record_fx_rate(actor=world.admin, base_currency_code="INR", quote_currency_code="USD", rate="0.0200000000", as_of=world.now - timedelta(days=3))
    line.refresh_from_db()
    assert line.amount == Decimal("1080.00") and line.fx_rate_applied == Decimal("0.0120000000")
    v = variance(fda)
    pilot = next(r for r in v["lines"] if r["category"] == "Pilotage")
    assert pilot["pda_amount"] == Decimal("1200.00") and pilot["fda_amount"] == Decimal("1080.00") and pilot["variance"] == Decimal("-120.00")
    dues = next(r for r in v["lines"] if r["category"] == "Port dues")
    assert dues["fda_amount"] == Decimal("0.00") and dues["variance"] == Decimal("-2400.00")
    assert v["total_variance"] == v["fda_total"] - v["pda_total"]
