"""Shared output shapes (API.md §0 'Common shapes'). Amounts are strings, never numbers."""
from decimal import Decimal

from rest_framework import serializers


def dec(value):
    if value is None:
        return None
    return str(value) if isinstance(value, Decimal) else str(Decimal(value))


def money(amount, currency_code):
    if amount is None:
        return None
    return {"amount": dec(amount), "currency_code": currency_code}


def dt(value):
    return value.isoformat().replace("+00:00", "Z") if value else None


def org_summary(org):
    if org is None:
        return None
    return {
        "id": org.pk,
        "type": org.type,
        "legal_name": org.legal_name,
        "trade_name": org.trade_name,
        "country_code": org.country_id,
        "city": org.city,
    }


def user_summary(user):
    if user is None:
        return None
    return {"id": user.pk, "display_name": user.display_name, "email": user.email, "role": user.role}


def file_ref(stored, request=None):
    if stored is None:
        return None
    from apps.documents.services import download_url

    return {
        "id": stored.pk,
        "original_filename": stored.original_filename,
        "content_type": stored.content_type,
        "size_bytes": stored.size_bytes,
        "download_url": download_url(stored, request),
    }


class MoneyField(serializers.DecimalField):
    def __init__(self, **kwargs):
        kwargs.setdefault("max_digits", 18)
        kwargs.setdefault("decimal_places", 2)
        super().__init__(**kwargs)


class RateField(serializers.DecimalField):
    def __init__(self, **kwargs):
        kwargs.setdefault("max_digits", 20)
        kwargs.setdefault("decimal_places", 10)
        super().__init__(**kwargs)


class MoneyInputSerializer(serializers.Serializer):
    amount = MoneyField()
    currency_code = serializers.CharField(max_length=3)


class NoteSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, default="")


class RequiredNoteSerializer(serializers.Serializer):
    note = serializers.CharField()


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField()


class OptionalReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")


def validated(serializer_class, data, **kwargs):
    serializer = serializer_class(data=data, **kwargs)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data
