"""Master data writes and FX rate selection (ARCHITECTURE.md §3.4)."""
import logging
from dataclasses import dataclass
from datetime import datetime, time, timezone as dt_timezone
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.audit import audit
from apps.core.exceptions import ValidationFailed
from apps.core.money import invert_rate, round_rate, to_decimal

from .fx_providers import FxProviderError, fetch_market_rate
from .models import Currency, FxRate

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AppliedRate:
    """The rate row used for provenance and the exact decimal applied (SCHEMA.md D9)."""

    fx_rate: FxRate | None
    applied: Decimal
    inverse: bool = False

    @property
    def note(self) -> str:
        if self.fx_rate is None:
            return "same currency"
        how = "inverse of " if self.inverse else ""
        return f"{how}rate #{self.fx_rate.pk} ({self.fx_rate}, source {self.fx_rate.source})"


IDENTITY = AppliedRate(None, Decimal("1"))


def _applied(rate: FxRate, base: str, quote: str) -> AppliedRate:
    if rate.base_currency_id == base and rate.quote_currency_id == quote:
        return AppliedRate(rate, round_rate(rate.rate), False)
    if rate.base_currency_id == quote and rate.quote_currency_id == base:
        return AppliedRate(rate, invert_rate(rate.rate), True)
    raise ValidationFailed(
        f"FX rate #{rate.pk} is {rate.base_currency_id}/{rate.quote_currency_id}, not {base}/{quote}.",
        {"fx_rate_id": ["Currency pair mismatch."]},
    )


def _pair(base, quote):
    return Q(base_currency_id=base, quote_currency_id=quote) | Q(base_currency_id=quote, quote_currency_id=base)


def end_of_day(day):
    """The transaction moment used for a date-only document (e.g. an invoice's issue date), capped at now."""
    return min(datetime.combine(day, time(23, 59, 59), tzinfo=dt_timezone.utc), timezone.now())


def fetch_and_record_market_rate(*, base: str, quote: str, as_of=None, actor=None) -> FxRate:
    """Fetch the public market rate for `as_of`'s date and store it as an fx_rates row dated `as_of`
    (the transaction time), so it becomes the latest rate for that transaction. Raises FxProviderError."""
    as_of = min(as_of or timezone.now(), timezone.now())
    for code in (base, quote):
        if not Currency.objects.filter(code=code, is_active=True).exists():
            raise ValidationFailed(f"Unknown or inactive currency {code}.")
    market = fetch_market_rate(base, quote, as_of.date())
    existing = FxRate.objects.filter(base_currency_id=base, quote_currency_id=quote, source=market.source, as_of=as_of).first()
    if existing:
        return existing
    try:
        with transaction.atomic():
            return record_fx_rate(actor=actor, base_currency_code=base, quote_currency_code=quote, rate=market.rate,
                                  as_of=as_of, source=market.source, source_reference=market.reference)
    except (IntegrityError, ValidationFailed):  # a concurrent request recorded the same row
        found = FxRate.objects.filter(base_currency_id=base, quote_currency_id=quote, source=market.source, as_of=as_of).first()
        if found:
            return found
        raise


def _ensure_rate_for_day(base, quote, as_of):
    """If nothing is recorded for this pair on the transaction's (UTC) day, fetch the market rate. Never raises."""
    day_start = datetime.combine(as_of.astimezone(dt_timezone.utc).date(), time.min, tzinfo=dt_timezone.utc)
    if FxRate.objects.filter(_pair(base, quote), as_of__gte=day_start, as_of__lte=as_of).exists():
        return
    try:
        fetch_and_record_market_rate(base=base, quote=quote, as_of=as_of)
    except (FxProviderError, ValidationFailed) as exc:
        logger.info("No market rate for %s/%s at %s (%s); using the latest recorded rate", base, quote, as_of, exc)


def select_rate(base: str, quote: str, as_of=None, auto_fetch=None) -> AppliedRate:
    """Latest rate with as_of <= `as_of` for base→quote; falls back to the inverse pair. Raises if none.

    With auto-fetch on (settings.FX_AUTO_FETCH), a pair with no rate recorded on the transaction's day
    first gets the public market rate for that day, which then is the latest and is selected."""
    if base == quote:
        return IDENTITY
    as_of = as_of or timezone.now()
    if settings.FX_AUTO_FETCH if auto_fetch is None else auto_fetch:
        _ensure_rate_for_day(base, quote, as_of)
    direct = FxRate.objects.filter(base_currency_id=base, quote_currency_id=quote, as_of__lte=as_of).order_by("-as_of", "-fetched_at", "-id").first()
    inverse = FxRate.objects.filter(base_currency_id=quote, quote_currency_id=base, as_of__lte=as_of).order_by("-as_of", "-fetched_at", "-id").first()
    candidates = [r for r in (direct, inverse) if r is not None]
    if not candidates:
        raise ValidationFailed(
            f"No FX rate for {base}→{quote} on or before {as_of:%Y-%m-%d %H:%M}.",
            {"fx": [f"missing {base}/{quote}"], "missing_pairs": [f"{base}/{quote}"]},
            code="fx_rate_missing",
        )
    # Prefer the most recent; on tie prefer the direct quote.
    best = max(candidates, key=lambda r: (r.as_of, r is direct))
    return _applied(best, base, quote)


def rate_by_id(rate_id: int, base: str, quote: str) -> AppliedRate:
    if base == quote:
        raise ValidationFailed("No FX rate may be applied to a same-currency amount.", {"fx_rate_id": ["Must be null."]})
    rate = FxRate.objects.filter(pk=rate_id).first()
    if rate is None:
        raise ValidationFailed(f"FX rate #{rate_id} does not exist.", {"fx_rate_id": ["Not found."]})
    return _applied(rate, base, quote)


def resolve_rate(base: str, quote: str, *, rate_id=None, as_of=None, auto_fetch=None) -> AppliedRate:
    if base == quote:
        if rate_id:
            raise ValidationFailed("No FX rate may be applied to a same-currency amount.", {"fx_rate_id": ["Must be null."]})
        return IDENTITY
    if rate_id:
        return rate_by_id(rate_id, base, quote)
    return select_rate(base, quote, as_of, auto_fetch=auto_fetch)


@transaction.atomic
def record_fx_rate(*, actor, base_currency_code, quote_currency_code, rate, as_of, source="MANUAL", source_reference=""):
    rate = to_decimal(rate)
    if rate <= 0:
        raise ValidationFailed("Rate must be positive.", {"rate": ["Must be > 0."]})
    if base_currency_code == quote_currency_code:
        raise ValidationFailed("Base and quote currencies must differ.")
    for code in (base_currency_code, quote_currency_code):
        if not Currency.objects.filter(code=code, is_active=True).exists():
            raise ValidationFailed(f"Unknown or inactive currency {code}.")
    if FxRate.objects.filter(
        base_currency_id=base_currency_code, quote_currency_id=quote_currency_code, source=source, as_of=as_of
    ).exists():
        raise ValidationFailed("A rate for this pair, source and timestamp already exists.", code="conflict")
    fx = FxRate.objects.create(
        base_currency_id=base_currency_code,
        quote_currency_id=quote_currency_code,
        rate=round_rate(rate),
        as_of=as_of,
        source=source,
        source_reference=source_reference or "",
        created_by_user=actor,
    )
    if actor is not None:
        audit(actor=actor, action="fx_rate.recorded", entity=fx, metadata={"rate": fx.rate, "pair": f"{base_currency_code}/{quote_currency_code}"})
    return fx
