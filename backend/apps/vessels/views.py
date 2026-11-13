from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.audit import audit, diff
from apps.core.enums import PORT_CALL_TERMINAL, Role, VesselType
from apps.core.exceptions import Conflict, NotFound
from apps.core.pagination import StandardPagination, apply_sort
from apps.core.permissions import approved
from apps.core.serializers import dec, dt, validated
from apps.masterdata.models import Country

from .models import Vessel

NUMERIC = ("grt", "nrt", "dwt", "loa_m", "beam_m", "max_draft_m")


class VesselInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    imo_number = serializers.RegexField(r"^[0-9]{7}$", required=False, allow_null=True, allow_blank=True)
    call_sign = serializers.CharField(max_length=16, required=False, allow_blank=True)
    flag_country_code = serializers.CharField(max_length=2, required=False, allow_null=True, allow_blank=True)
    vessel_type = serializers.ChoiceField(choices=VesselType.choices)
    grt = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True, min_value=0)
    nrt = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True, min_value=0)
    dwt = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True, min_value=0)
    loa_m = serializers.DecimalField(max_digits=8, decimal_places=2, required=False, allow_null=True, min_value=0)
    beam_m = serializers.DecimalField(max_digits=8, decimal_places=2, required=False, allow_null=True, min_value=0)
    max_draft_m = serializers.DecimalField(max_digits=8, decimal_places=2, required=False, allow_null=True, min_value=0)

    def validate_flag_country_code(self, value):
        if value and not Country.objects.filter(code=value.upper()).exists():
            raise serializers.ValidationError("Unknown country.")
        return value.upper() if value else None


def vessel_data(v):
    return {
        "id": v.pk,
        "name": v.name,
        "imo_number": v.imo_number,
        "call_sign": v.call_sign,
        "flag_country_code": v.flag_country_id,
        "vessel_type": v.vessel_type,
        **{f: dec(getattr(v, f)) for f in NUMERIC},
        "owner_organization_id": v.owner_organization_id,
        "created_at": dt(v.created_at),
    }


def _values(data):
    values = {k: v for k, v in data.items() if k != "flag_country_code"}
    if "flag_country_code" in data:
        values["flag_country_id"] = data["flag_country_code"]
    if "imo_number" in values:
        values["imo_number"] = values["imo_number"] or None
    return values


def _check_unique(owner_id, data, exclude=None):
    qs = Vessel.objects.filter(deleted_at__isnull=True)
    if exclude:
        qs = qs.exclude(pk=exclude)
    if data.get("imo_number") and qs.filter(imo_number=data["imo_number"]).exists():
        raise Conflict("A vessel with this IMO number already exists.")
    if data.get("name") and qs.filter(owner_organization_id=owner_id, name__iexact=data["name"]).exists():
        raise Conflict("You already have a vessel with this name.")


def _scoped(request):
    qs = Vessel.objects.filter(deleted_at__isnull=True)
    if request.user.role == Role.ADMIN:
        return qs
    return qs.filter(owner_organization_id=request.user.organization_id)


class VesselListView(APIView):
    permission_classes = approved(Role.OWNER, Role.ADMIN)

    def get(self, request):
        qs = _scoped(request)
        if request.query_params.get("q"):
            q = request.query_params["q"]
            qs = qs.filter(Q(name__icontains=q) | Q(imo_number__icontains=q))
        qs = apply_sort(qs, request, {"name": "name", "created_at": "created_at", "id": "id"}, "name")
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([vessel_data(v) for v in page])

    @transaction.atomic
    def post(self, request):
        if request.user.role != Role.OWNER:
            raise NotFound()
        data = validated(VesselInputSerializer, request.data)
        values = _values(data)
        _check_unique(request.user.organization_id, values)
        vessel = Vessel.objects.create(owner_organization_id=request.user.organization_id, **values)
        audit(actor=request.user, action="vessel.created", entity=vessel, metadata={"name": vessel.name})
        return Response(vessel_data(vessel), status=status.HTTP_201_CREATED)


class VesselDetailView(APIView):
    permission_classes = approved(Role.OWNER, Role.ADMIN)

    def _get(self, request, pk):
        vessel = _scoped(request).filter(pk=pk).first()
        if vessel is None:
            raise NotFound()
        return vessel

    def get(self, request, pk):
        return Response(vessel_data(self._get(request, pk)))

    @transaction.atomic
    def patch(self, request, pk):
        vessel = self._get(request, pk)
        if request.user.role != Role.OWNER:
            raise NotFound()
        data = validated(VesselInputSerializer, request.data, partial=True)
        values = _values(data)
        _check_unique(vessel.owner_organization_id, values, exclude=vessel.pk)
        changes = diff(vessel, values)
        vessel.save()
        audit(actor=request.user, action="vessel.updated", entity=vessel, changes=changes)
        return Response(vessel_data(vessel))

    @transaction.atomic
    def delete(self, request, pk):
        vessel = self._get(request, pk)
        if request.user.role != Role.OWNER:
            raise NotFound()
        if vessel.port_calls.exclude(status__in=PORT_CALL_TERMINAL).exists():
            raise Conflict("This vessel has an active port call.")
        vessel.deleted_at = timezone.now()
        vessel.save(update_fields=["deleted_at", "updated_at"])
        audit(actor=request.user, action="vessel.deleted", entity=vessel)
        return Response(status=status.HTTP_204_NO_CONTENT)
