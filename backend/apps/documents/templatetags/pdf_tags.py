from decimal import Decimal

from django import template

from apps.core.money import minor_units

register = template.Library()


def _fmt(value, currency):
    if value is None:
        return ""
    value = Decimal(value)
    places = minor_units(currency) if currency else 2
    return f"{value:,.{places}f}"


@register.filter
def money(value, currency=""):
    text = _fmt(value, currency)
    return f"{currency} {text}".strip() if text else ""


@register.filter
def signed_money(value, currency=""):
    if value is None:
        return ""
    value = Decimal(value)
    sign = "+" if value > 0 else "−" if value < 0 else ""
    return f"{sign}{currency} {_fmt(abs(value), currency)}"


@register.filter
def rate(value):
    return f"{Decimal(value).normalize():f}" if value is not None else ""


@register.filter
def qty(value):
    return f"{Decimal(value).normalize():f}" if value is not None else ""
