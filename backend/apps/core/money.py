"""Money helpers. Never use floats (ARCHITECTURE.md §3.4).

Conventions
- Amounts: Decimal quantized to the currency's minor units with ROUND_HALF_UP, once per line.
- Rates: Decimal with 10 decimal places; `rate` = quote units per 1 base unit.
- Totals are sums of already-rounded lines so the printed document foots exactly.
"""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

RATE_PLACES = Decimal("0.0000000001")
_minor_units_cache: dict[str, int] = {}


def to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        raise TypeError("Floats are not allowed for money; pass str or Decimal")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid decimal value: {value!r}") from exc


def minor_units(currency_code: str) -> int:
    if currency_code not in _minor_units_cache:
        from apps.masterdata.models import Currency

        units = Currency.objects.filter(code=currency_code).values_list("minor_units", flat=True).first()
        _minor_units_cache[currency_code] = 2 if units is None else int(units)
    return _minor_units_cache[currency_code]


def clear_minor_units_cache():
    _minor_units_cache.clear()


def quantum(currency_code: str) -> Decimal:
    units = minor_units(currency_code)
    return Decimal(1).scaleb(-units) if units else Decimal(1)


def round_money(amount, currency_code: str) -> Decimal:
    return to_decimal(amount).quantize(quantum(currency_code), rounding=ROUND_HALF_UP)


def round_rate(rate) -> Decimal:
    return to_decimal(rate).quantize(RATE_PLACES, rounding=ROUND_HALF_UP)


def convert(amount, rate, target_currency: str) -> Decimal:
    """amount (base currency) × rate → target (quote) currency, rounded once."""
    return round_money(to_decimal(amount) * to_decimal(rate), target_currency)


def invert_rate(rate) -> Decimal:
    rate = to_decimal(rate)
    if rate <= 0:
        raise ValueError("Rate must be positive")
    return round_rate(Decimal(1) / rate)


def sum_money(amounts, currency_code: str) -> Decimal:
    total = Decimal("0")
    for amount in amounts:
        total += to_decimal(amount)
    return round_money(total, currency_code)
