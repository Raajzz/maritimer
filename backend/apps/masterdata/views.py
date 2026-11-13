from django.db.models import Q
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.enums import FxSource, Role
from apps.core.exceptions import NotFound
from apps.core.pagination import StandardPagination
from apps.core.permissions import approved
from apps.core.serializers import RateField, dec, dt, validated

from .models import CargoType, Country, Currency, FxRate, Location, Port, ServiceCategory
from .services import record_fx_rate, resolve_rate


def country_data(c):
    return {"code": c.code, "iso3": c.iso3, "name": c.name, "is_active": c.is_active}


def location_data(l):
    return {"id": l.pk, "country_code": l.country_id, "name": l.name, "region": l.region, "is_active": l.is_active}


def port_data(p):
    return {
        "id": p.pk,
        "name": p.name,
        "unlocode": p.unlocode,
        "timezone": p.timezone,
        "latitude": dec(p.latitude),
        "longitude": dec(p.longitude),
        "is_active": p.is_active,
        "location": {"id": p.location_id, "name": p.location.name, "country_code": p.location.country_id},
    }


def service_data(s):
    return {"id": s.pk, "code": s.code, "name": s.name, "description": s.description, "is_vendor_service": s.is_vendor_service,
            "is_agent_fee": s.is_agent_fee, "sort_order": s.sort_order, "is_active": s.is_active}


def cargo_data(c):
    return {"id": c.pk, "code": c.code, "name": c.name, "is_active": c.is_active}


def currency_data(c):
    return {"code": c.code, "name": c.name, "symbol": c.symbol, "minor_units": c.minor_units, "is_active": c.is_active}


def fx_data(r):
    return {
        "id": r.pk,
        "base_currency_code": r.base_currency_id,
        "quote_currency_code": r.quote_currency_id,
        "rate": dec(r.rate),
        "source": r.source,
        "source_reference": r.source_reference,
        "as_of": dt(r.as_of),
        "fetched_at": dt(r.fetched_at),
    }


def _include_inactive(request):
    return request.user.role == Role.ADMIN and request.query_params.get("include_inactive") == "true"


class CountryListView(APIView):
    permission_classes = [IsAuthenticated]  # reference data is needed during onboarding (PROGRESS.md C12)

    def get(self, request):
        qs = Country.objects.all() if _include_inactive(request) else Country.objects.filter(is_active=True)
        return Response([country_data(c) for c in qs])


class LocationListView(APIView):
    permission_classes = [IsAuthenticated]  # reference data is needed during onboarding (PROGRESS.md C12)

    def get(self, request):
        qs = Location.objects.all() if _include_inactive(request) else Location.objects.filter(is_active=True)
        if request.query_params.get("country"):
            qs = qs.filter(country_id=request.query_params["country"].upper())
        if request.query_params.get("q"):
            qs = qs.filter(name__icontains=request.query_params["q"])
        return Response([location_data(l) for l in qs])


class PortListView(APIView):
    permission_classes = [IsAuthenticated]  # reference data is needed during onboarding (PROGRESS.md C12)

    def get(self, request):
        qs = Port.objects.select_related("location")
        if not _include_inactive(request):
            qs = qs.filter(is_active=True)
        if request.query_params.get("location_id"):
            qs = qs.filter(location_id=request.query_params["location_id"])
        if request.query_params.get("q"):
            q = request.query_params["q"]
            qs = qs.filter(Q(name__icontains=q) | Q(unlocode__icontains=q))
        return Response([port_data(p) for p in qs])


class ServiceCategoryListView(APIView):
    permission_classes = [IsAuthenticated]  # reference data is needed during onboarding (PROGRESS.md C12)

    def get(self, request):
        qs = ServiceCategory.objects.all() if _include_inactive(request) else ServiceCategory.objects.filter(is_active=True)
        if request.query_params.get("vendor_only") == "true":
            qs = qs.filter(is_vendor_service=True)
        return Response([service_data(s) for s in qs])


class CargoTypeListView(APIView):
    permission_classes = [IsAuthenticated]  # reference data is needed during onboarding (PROGRESS.md C12)

    def get(self, request):
        qs = CargoType.objects.all() if _include_inactive(request) else CargoType.objects.filter(is_active=True)
        return Response([cargo_data(c) for c in qs])


class CurrencyListView(APIView):
    permission_classes = [IsAuthenticated]  # reference data is needed during onboarding (PROGRESS.md C12)

    def get(self, request):
        qs = Currency.objects.all() if _include_inactive(request) else Currency.objects.filter(is_active=True)
        return Response([currency_data(c) for c in qs])


class FxRateInputSerializer(serializers.Serializer):
    base_currency_code = serializers.CharField(max_length=3)
    quote_currency_code = serializers.CharField(max_length=3)
    rate = RateField()
    as_of = serializers.DateTimeField()
    source = serializers.ChoiceField(choices=FxSource.choices, default=FxSource.MANUAL)
    source_reference = serializers.CharField(required=False, allow_blank=True, default="", max_length=200)


class FxRateListView(APIView):
    permission_classes = approved(Role.AGENT, Role.ADMIN)

    def get(self, request):
        qs = FxRate.objects.all()
        params = request.query_params
        if params.get("base"):
            qs = qs.filter(base_currency_id=params["base"].upper())
        if params.get("quote"):
            qs = qs.filter(quote_currency_id=params["quote"].upper())
        if params.get("as_of_lte"):
            qs = qs.filter(as_of__lte=params["as_of_lte"])
        qs = qs.order_by("-as_of", "-id")
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([fx_data(r) for r in page])

    def post(self, request):
        data = validated(FxRateInputSerializer, request.data)
        fx = record_fx_rate(actor=request.user, **{**data, "base_currency_code": data["base_currency_code"].upper(),
                                                     "quote_currency_code": data["quote_currency_code"].upper()})
        return Response(fx_data(fx), status=status.HTTP_201_CREATED)


class FxRateLatestView(APIView):
    permission_classes = approved(Role.AGENT, Role.ADMIN)

    def get(self, request):
        params = request.query_params
        base, quote = (params.get("base") or "").upper(), (params.get("quote") or "").upper()
        if not base or not quote:
            raise NotFound("Pass base and quote.")
        as_of = serializers.DateTimeField().to_internal_value(params["as_of_lte"]) if params.get("as_of_lte") else None
        applied = resolve_rate(base, quote, as_of=as_of)
        return Response({
            "rate": fx_data(applied.fx_rate) if applied.fx_rate else None,
            "applied_rate": dec(applied.applied),
            "inverse": applied.inverse,
            "note": applied.note,
        })
