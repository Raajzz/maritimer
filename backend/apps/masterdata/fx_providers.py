"""Market FX rates from free, keyless public APIs (ARCHITECTURE.md §3.4).

1. Frankfurter (https://frankfurter.dev): European Central Bank reference rates, published each
   working day around 16:00 CET. Official, historical by date, but only ~30 currencies (no AED, LKR).
2. fawazahmed0 currency-api (https://github.com/fawazahmed0/exchange-api), served from jsDelivr with a
   Cloudflare Pages mirror: daily rates for 200+ currencies, historical by date. Fallback.

Both return the rate published for the requested date, or the latest one before it (weekends,
holidays). JSON numbers are parsed straight into Decimal, so no float ever touches a rate.
"""
import json
import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import requests
from django.conf import settings

from apps.core.enums import FxSource

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MarketRate:
    rate: Decimal          # quote units per 1 base unit
    source: str            # FxSource value
    reference: str         # human-readable provenance, stored on the fx_rates row
    published_on: date     # the date the provider's rate is for


class FxProviderError(Exception):
    pass


def _get_json(url):
    response = requests.get(url, timeout=settings.FX_FETCH_TIMEOUT_SECONDS, headers={"Accept": "application/json"})
    response.raise_for_status()
    return json.loads(response.text, parse_float=Decimal, parse_int=Decimal)


def _frankfurter(base, quote, on):
    data = _get_json(f"https://api.frankfurter.dev/v1/{on.isoformat()}?base={base}&symbols={quote}")
    rate = (data.get("rates") or {}).get(quote)
    if rate is None:
        raise FxProviderError(f"Frankfurter has no {base}/{quote}")
    published = date.fromisoformat(data["date"])
    return MarketRate(Decimal(rate), FxSource.ECB, f"ECB reference rate {published.isoformat()} via frankfurter.dev", published)


def _currency_api(base, quote, on):
    b, q = base.lower(), quote.lower()
    tag = "latest" if on >= date.today() else on.isoformat()
    last_error = None
    for url in (
        f"https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@{tag}/v1/currencies/{b}.json",
        f"https://{tag}.currency-api.pages.dev/v1/currencies/{b}.json",
    ):
        try:
            data = _get_json(url)
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            continue
        rate = (data.get(b) or {}).get(q)
        if rate is None:
            raise FxProviderError(f"currency-api has no {base}/{quote}")
        published = date.fromisoformat(data["date"])
        return MarketRate(Decimal(rate), FxSource.CURRENCY_API, f"Market rate {published.isoformat()} via fawazahmed0 currency-api", published)
    raise FxProviderError(f"currency-api unreachable: {last_error}")


PROVIDERS = (_frankfurter, _currency_api)


def fetch_market_rate(base: str, quote: str, on: date) -> MarketRate:
    """Rate for base→quote published on `on` (or the latest working day before it). Tries each provider."""
    errors = []
    for provider in PROVIDERS:
        try:
            result = provider(base, quote, on)
            if result.rate > 0:
                return result
            errors.append(f"{provider.__name__}: non-positive rate")
        except (requests.RequestException, FxProviderError, ValueError, KeyError) as exc:
            errors.append(f"{provider.__name__}: {exc}")
    logger.warning("FX fetch failed for %s/%s on %s: %s", base, quote, on, "; ".join(errors))
    raise FxProviderError("; ".join(errors))
