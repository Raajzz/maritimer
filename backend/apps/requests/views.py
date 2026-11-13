from django.db.models import Q
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.enums import RequestType, Role
from apps.core.exceptions import NotFound
from apps.core.pagination import StandardPagination, apply_sort
from apps.core.permissions import approved
from apps.core.serializers import NoteSerializer, dec, dt, org_summary, user_summary, validated

from . import services
from .models import Request


class ServiceItemSerializer(serializers.Serializer):
    service_category_id = serializers.IntegerField()
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3, required=False, allow_null=True)
    unit = serializers.CharField(max_length=16, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class PortCallDetailSerializer(serializers.Serializer):
    vessel_id = serializers.IntegerField()
    port_id = serializers.IntegerField()
    eta = serializers.DateTimeField()
    etd = serializers.DateTimeField()
    cargo_type_id = serializers.IntegerField()
    cargo_description = serializers.CharField(max_length=300, required=False, allow_blank=True)
    cargo_quantity = serializers.DecimalField(max_digits=14, decimal_places=3, required=False, allow_null=True)
    cargo_unit = serializers.CharField(max_length=16, required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs["etd"] <= attrs["eta"]:
            raise serializers.ValidationError({"etd": "ETD must be after ETA."})
        return attrs


class RequestCreateSerializer(serializers.Serializer):
    request_type = serializers.ChoiceField(choices=RequestType.choices)
    to_organization_id = serializers.IntegerField()
    port_call_id = serializers.IntegerField(required=False, allow_null=True)
    subject = serializers.CharField(max_length=200, required=False, allow_blank=True)
    message = serializers.CharField(required=False, allow_blank=True)
    details = PortCallDetailSerializer(required=False)
    services = ServiceItemSerializer(many=True, required=False)
    payload = serializers.JSONField(required=False)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate(self, attrs):
        if attrs["request_type"] == RequestType.PORT_CALL and not attrs.get("details"):
            raise serializers.ValidationError({"details": "Required for PORT_CALL requests."})
        if attrs["request_type"] == RequestType.VENDOR_SERVICE and not attrs.get("port_call_id"):
            raise serializers.ValidationError({"port_call_id": "Required for VENDOR_SERVICE requests."})
        return attrs


def request_row(r):
    detail = getattr(r, "port_call_detail", None) if r.request_type == RequestType.PORT_CALL else None
    return {
        "id": r.pk,
        "reference": r.reference,
        "request_type": r.request_type,
        "status": r.status,
        "subject": r.subject,
        "from_organization": org_summary(r.from_organization),
        "from_role": r.from_role,
        "to_organization": org_summary(r.to_organization),
        "to_role": r.to_role,
        "port_call": {"id": r.port_call_id, "reference": r.port_call.reference, "status": r.port_call.status} if r.port_call_id else None,
        "vessel": {"id": detail.vessel_id, "name": detail.vessel.name} if detail else None,
        "port": {"id": detail.port_id, "name": detail.port.name} if detail else None,
        "eta": dt(detail.eta) if detail else None,
        "created_at": dt(r.created_at),
        "responded_at": dt(r.responded_at),
    }


def request_detail(r):
    from apps.chat.models import ChatThread

    detail = getattr(r, "port_call_detail", None) if r.request_type == RequestType.PORT_CALL else None
    thread = ChatThread.objects.filter(request=r).first() if r.request_type == RequestType.VENDOR_SERVICE else (
        ChatThread.objects.filter(port_call_id=r.port_call_id, kind="PORT_CALL").first() if r.port_call_id else None
    )
    return {
        **request_row(r),
        "from_user": user_summary(r.from_user),
        "to_user": user_summary(r.to_user),
        "message": r.message,
        "payload": r.payload,
        "response_note": r.response_note,
        "expires_at": dt(r.expires_at),
        "details": {
            "vessel": {"id": detail.vessel_id, "name": detail.vessel.name, "imo_number": detail.vessel.imo_number,
                       "vessel_type": detail.vessel.vessel_type},
            "port": {"id": detail.port_id, "name": detail.port.name, "unlocode": detail.port.unlocode},
            "eta": dt(detail.eta),
            "etd": dt(detail.etd),
            "cargo_type": {"id": detail.cargo_type_id, "name": detail.cargo_type.name},
            "cargo_description": detail.cargo_description,
            "cargo_quantity": dec(detail.cargo_quantity),
            "cargo_unit": detail.cargo_unit,
        } if detail else None,
        "services": [
            {"service_category": {"id": s.service_category_id, "code": s.service_category.code, "name": s.service_category.name},
             "quantity": dec(s.quantity), "unit": s.unit, "notes": s.notes}
            for s in r.services.select_related("service_category")
        ],
        "chat_thread_id": thread.pk if thread else None,
    }


def scoped_requests(user):
    qs = Request.objects.select_related(
        "from_organization", "to_organization", "port_call", "from_user", "to_user",
        "port_call_detail__vessel", "port_call_detail__port", "port_call_detail__cargo_type",
    )
    if user.role == Role.ADMIN:
        return qs
    org_id = user.organization_id
    return qs.filter(Q(from_organization_id=org_id) | Q(to_organization_id=org_id))


def get_request(user, pk):
    r = scoped_requests(user).filter(pk=pk).first()
    if r is None:
        raise NotFound()
    return r


class RequestListView(APIView):
    permission_classes = approved(Role.OWNER, Role.AGENT, Role.MERCHANT, Role.ADMIN)

    def get(self, request):
        qs = scoped_requests(request.user)
        params = request.query_params
        org_id = request.user.organization_id
        if params.get("direction") == "incoming":
            qs = qs.filter(to_organization_id=org_id)
        elif params.get("direction") == "outgoing":
            qs = qs.filter(from_organization_id=org_id)
        for key in ("request_type", "status", "port_call_id"):
            if params.get(key):
                qs = qs.filter(**{key: params[key]})
        qs = apply_sort(qs, request, {"created_at": "created_at", "status": "status", "id": "id"}, "-created_at")
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([request_row(r) for r in page])

    def post(self, request):
        data = validated(RequestCreateSerializer, request.data)
        created = services.create_request(actor=request.user, data=data)
        return Response(request_detail(get_request(request.user, created.pk)), status=status.HTTP_201_CREATED)


class RequestDetailView(APIView):
    permission_classes = approved(Role.OWNER, Role.AGENT, Role.MERCHANT, Role.ADMIN)

    def get(self, request, pk):
        return Response(request_detail(get_request(request.user, pk)))


class RequestAcceptView(APIView):
    permission_classes = approved(Role.OWNER, Role.AGENT, Role.MERCHANT)

    def post(self, request, pk):
        data = validated(NoteSerializer, request.data)
        r, port_call, thread = services.accept_request(actor=request.user, request=get_request(request.user, pk), note=data["note"])
        body = request_detail(get_request(request.user, r.pk))
        body["port_call"] = {"id": port_call.pk, "reference": port_call.reference, "status": port_call.status} if port_call else None
        body["chat_thread_id"] = thread.pk
        return Response(body)


class RequestDeclineView(APIView):
    permission_classes = approved(Role.OWNER, Role.AGENT, Role.MERCHANT)

    def post(self, request, pk):
        data = validated(NoteSerializer, request.data)
        services.decline_request(actor=request.user, request=get_request(request.user, pk), note=data["note"])
        return Response(request_detail(get_request(request.user, pk)))


class RequestWithdrawView(APIView):
    permission_classes = approved(Role.OWNER, Role.AGENT, Role.MERCHANT)

    def post(self, request, pk):
        services.withdraw_request(actor=request.user, request=get_request(request.user, pk))
        return Response(request_detail(get_request(request.user, pk)))
