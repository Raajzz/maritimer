"""Market FX rates fetched at transaction time (masterdata/fx_providers.py). HTTP is always mocked."""
import json
from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

import pytest
import requests

from apps.core.enums import AccountKind, FxSource
from apps.core.money import round_money
from apps.disbursements import services as da
from apps.masterdata import fx_providers
from apps.masterdata.fx_providers import FxProviderError, MarketRate, fetch_market_rate
from apps.masterdata.models import Currency, FxRate
from apps.masterdata.services import record_fx_rate, select_rate


class FakeResponse:
    def __init__(self, payload, status=200):
        self.text = json.dumps(payload) if not isinstance(payload, str) else payload
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.HTTPError(f"HTTP {self.status}")


def fake_get(routes):
    def get(url, **kwargs):
        for fragment, response in routes.items():
            if fragment in url:
                if isinstance(response, Exception):
                    raise response
                return response
        raise requests.ConnectionError(f"unexpected URL {url}")
    return get


def test_frankfurter_rate_is_parsed_as_exact_decimal():
    routes = {"frankfurter.dev/v1/2026-11-10?base=INR&symbols=USD": FakeResponse('{"amount":1.0,"base":"INR","date":"2026-11-10","rates":{"USD":0.010646}}')}
    with mock.patch.object(fx_providers.requests, "get", side_effect=fake_get(routes)):
        market = fetch_market_rate("INR", "USD", date(2026, 11, 10))
    assert market.rate == Decimal("0.010646") and isinstance(market.rate, Decimal)
    assert market.source == FxSource.ECB
    assert market.published_on == date(2026, 11, 10)
    assert "ECB" in market.reference


def test_falls_back_to_currency_api_for_currencies_ecb_lacks():
    routes = {
        "frankfurter.dev": FakeResponse({"amount": 1.0, "base": "USD", "date": "2026-11-10", "rates": {}}),
        "currency-api@2026-11-10/v1/currencies/aed.json": FakeResponse('{"date":"2026-11-10","aed":{"usd":0.27229408}}'),
    }
    with mock.patch.object(fx_providers.requests, "get", side_effect=fake_get(routes)):
        market = fetch_market_rate("AED", "USD", date(2026, 11, 10))
    assert market.rate == Decimal("0.27229408")
    assert market.source == FxSource.CURRENCY_API


def test_currency_api_mirror_is_used_when_jsdelivr_is_down():
    routes = {
        "frankfurter.dev": requests.ConnectionError("down"),
        "cdn.jsdelivr.net": requests.ConnectionError("down"),
        "2026-11-10.currency-api.pages.dev/v1/currencies/sgd.json": FakeResponse('{"date":"2026-11-10","sgd":{"usd":0.78231}}'),
    }
    with mock.patch.object(fx_providers.requests, "get", side_effect=fake_get(routes)):
        assert fetch_market_rate("SGD", "USD", date(2026, 11, 10)).rate == Decimal("0.78231")


def test_all_providers_failing_raises():
    with mock.patch.object(fx_providers.requests, "get", side_effect=requests.ConnectionError("offline")):
        with pytest.raises(FxProviderError):
            fetch_market_rate("INR", "USD", date(2026, 11, 10))


def market(rate, source=FxSource.ECB):
    return MarketRate(Decimal(rate), source, "test market rate", date.today())


@pytest.mark.django_db
def test_auto_fetch_records_the_market_rate_as_the_latest(world, settings):
    settings.FX_AUTO_FETCH = True
    with mock.patch("apps.masterdata.services.fetch_market_rate", return_value=market("0.0106460000")) as fetch:
        applied = select_rate("INR", "USD", world.now)
        again = select_rate("INR", "USD", world.now)  # same day: reuses the stored row, no second call
    assert fetch.call_count == 1
    assert applied.applied == Decimal("0.0106460000")
    assert applied.fx_rate.source == FxSource.ECB
    assert applied.fx_rate.as_of == world.now  # dated at the transaction time
    assert again.fx_rate == applied.fx_rate
    assert applied.fx_rate.created_by_user is None


@pytest.mark.django_db
def test_auto_fetch_failure_falls_back_to_latest_recorded_rate(world, settings):
    settings.FX_AUTO_FETCH = True
    with mock.patch("apps.masterdata.services.fetch_market_rate", side_effect=FxProviderError("offline")):
        applied = select_rate("INR", "USD", world.now)
    assert applied.fx_rate == world.rate_old


@pytest.mark.django_db
def test_manual_rate_recorded_that_day_is_used_without_fetching(world, settings):
    settings.FX_AUTO_FETCH = True
    manual = record_fx_rate(actor=world.agent, base_currency_code="INR", quote_currency_code="USD", rate="0.0119",
                            as_of=world.now - timedelta(minutes=5))
    with mock.patch("apps.masterdata.services.fetch_market_rate") as fetch:
        applied = select_rate("INR", "USD", world.now)
    fetch.assert_not_called()
    assert applied.fx_rate == manual


@pytest.mark.django_db
def test_fda_converts_each_invoice_at_its_issue_date_rate(world):
    out = world.stage("DEPARTED")  # ATD = now-2d, invoice issued today
    # A rate recorded after departure but before the invoice date: the invoice uses it (ATD rule would not).
    after_atd = record_fx_rate(actor=world.agent, base_currency_code="INR", quote_currency_code="USD", rate="0.0130000000",
                               as_of=world.now - timedelta(days=1))
    fda, _ = da.generate_fda(actor=world.agent, port_call=out["pc"])
    line = fda.line_items.get(vendor_invoice=out["invoice"])
    assert line.fx_rate_id == after_atd.pk
    assert line.fx_rate_applied == Decimal("0.0130000000")
    assert "issue date" in fda.fx_policy_note


@pytest.mark.django_db
def test_fetch_endpoint_records_market_rate_for_agents_only(world):
    with mock.patch("apps.masterdata.services.fetch_market_rate", return_value=market("0.7823100000", FxSource.CURRENCY_API)):
        response = world.client(world.agent).post("/api/v1/fx-rates/fetch", {"base_currency_code": "sgd", "quote_currency_code": "USD"}, format="json")
        denied = world.client(world.owner).post("/api/v1/fx-rates/fetch", {"base_currency_code": "SGD", "quote_currency_code": "USD"}, format="json")
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["source"] == "CURRENCY_API" and body["rate"] == "0.7823100000"
    assert body["base_currency_code"] == "SGD"
    assert denied.status_code in (403, 404)
    assert FxRate.objects.filter(base_currency_id="SGD", quote_currency_id="USD").count() == 1


@pytest.mark.django_db
def test_fetch_endpoint_reports_unavailable_rate(world):
    with mock.patch("apps.masterdata.services.fetch_market_rate", side_effect=FxProviderError("offline")):
        response = world.client(world.agent).post("/api/v1/fx-rates/fetch", {"base_currency_code": "INR", "quote_currency_code": "USD"}, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "fx_fetch_failed"


@pytest.mark.django_db
def test_main_currencies_are_seeded_with_correct_minor_units(world):
    codes = set(Currency.objects.filter(is_active=True).values_list("code", flat=True))
    assert {"USD", "EUR", "GBP", "INR", "SGD", "AED", "CNY", "JPY", "MYR"} <= codes
    assert round_money("1500.5", "JPY") == Decimal("1501")
    assert round_money("1500.555", "GBP") == Decimal("1500.56")


@pytest.mark.django_db
def test_non_inr_vendor_invoice_converts_to_usd(world):
    """A Singapore vendor billing in SGD on a USD port call."""
    record_fx_rate(actor=world.agent, base_currency_code="USD", quote_currency_code="SGD", rate="1.2783",
                   as_of=world.now - timedelta(days=3))
    out = world.stage("DEPARTED")
    invoice = out["invoice"]
    type(invoice).objects.filter(pk=invoice.pk).update(currency_id="SGD", total_amount=Decimal("1000.00"), subtotal_amount=Decimal("1000.00"))
    fda, _ = da.generate_fda(actor=world.agent, port_call=out["pc"])
    line = fda.line_items.get(vendor_invoice=invoice)
    assert line.local_currency_id == "SGD"
    # inverse of USD→SGD 1.2783 = 0.7822889775 (10 dp); 1000 × that = 782.29
    assert line.fx_rate_applied == Decimal("0.7822889775")
    assert line.amount == Decimal("782.29")
    assert da.current_account(out["pc"], AccountKind.FDA).currency_id == "USD"
