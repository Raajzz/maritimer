"""Admin-only endpoints (API.md §3 writes, §4)."""
from django.db import transaction
from django.db.models import Count, Q
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import services as account_services
from apps.accounts.models import Organization, User, VerificationDocument
from apps.accounts.serializers import (
    CoverageInputSerializer,
    OrganizationInputSerializer,
    ProfileInputSerializer,
    coverage_data,
    document_data,
    organization_data,
    profile_data,
    user_admin_row,
)
from apps.core.audit import audit, diff
from apps.core.enums import OrgType, ReviewStatus, Role, UserStatus, VerificationStatus
from apps.core.exceptions import NotFound
from apps.core.models import AuditLog
from apps.core.pagination import StandardPagination, apply_sort
from apps.core.permissions import approved
from apps.core.serializers import NoteSerializer, OptionalReasonSerializer, ReasonSerializer, user_summary, validated
from apps.masterdata.models import CargoType, Currency, Location, Port, ServiceCategory
from apps.masterdata.views import cargo_data, currency_data, location_data, port_data, service_data
from apps.portcalls.models import PortCall
from apps.portcalls.views import audit_row
from apps.requests.models import RequestRolePolicy

ADMIN = approved(Role.ADMIN)


def _paginate(view, request, qs, fn):
    paginator = StandardPagination()
    page = paginator.paginate_queryset(qs, request, view=view)
    return paginator.get_paginated_response([fn(x) for x in page])


class AdminDashboardView(APIView):
    permission_classes = ADMIN

    def get(self, request):
        users_by_role = dict(User.objects.filter(deleted_at__isnull=True).values_list("role").annotate(c=Count("id")).values_list("role", "c"))
        return Response({
            "pending_users": User.objects.filter(status=UserStatus.PENDING_REVIEW).count(),
            "pending_organizations": Organization.objects.filter(verification_status=VerificationStatus.PENDING_REVIEW).count(),
            "pending_documents": VerificationDocument.objects.filter(status=ReviewStatus.PENDING).count(),
            "users_by_role": {str(k): v for k, v in users_by_role.items()},
            "port_calls_by_status": dict(PortCall.objects.values_list("status").annotate(c=Count("id")).values_list("status", "c")),
            "recent_audit": [audit_row(e) for e in AuditLog.objects.select_related("actor_user").order_by("-created_at", "-id")[:20]],
        })


# ---- Users ------------------------------------------------------------------------


class AdminUserListView(APIView):
    permission_classes = ADMIN

    def get(self, request):
        qs = User.objects.filter(deleted_at__isnull=True).prefetch_related("memberships__organization")
        params = request.query_params
        if params.get("status"):
            qs = qs.filter(status__in=params["status"].split(","))
        if params.get("role"):
            qs = qs.filter(role=params["role"])
        if params.get("q"):
            q = params["q"]
            qs = qs.filter(Q(email__icontains=q) | Q(display_name__icontains=q) | Q(memberships__organization__legal_name__icontains=q)).distinct()
        qs = apply_sort(qs, request, {"created_at": "created_at", "email": "email", "display_name": "display_name", "status": "status"}, "-created_at")
        return _paginate(self, request, qs, user_admin_row)


def _get_user(pk):
    user = User.objects.filter(pk=pk, deleted_at__isnull=True).first()
    if user is None:
        raise NotFound()
    return user


def user_detail(user, request):
    org = user.organization
    entries = AuditLog.objects.filter(Q(entity_type="users", entity_id=user.pk) | Q(actor_user=user)).select_related("actor_user").order_by("-created_at")[:25]
    return {
        **user_admin_row(user),
        "organization_detail": organization_data(org) if org else None,
        "profile": profile_data(org) if org else None,
        "coverage": coverage_data(org) if org else None,
        "documents": [document_data(d, request) for d in org.verification_documents.select_related("file", "uploaded_by_user")] if org else [],
        "audit": [audit_row(e) for e in entries],
    }


class AdminUserDetailView(APIView):
    permission_classes = ADMIN

    def get(self, request, pk):
        return Response(user_detail(_get_user(pk), request))


def _user_action(func, serializer, field_map):
    class _View(APIView):
        permission_classes = ADMIN

        def post(self, request, pk):
            data = validated(serializer, request.data)
            kwargs = {field_map[k]: v for k, v in data.items() if k in field_map}
            func(actor=request.user, user=_get_user(pk), **kwargs)
            user = _get_user(pk)
            return Response(user_detail(user, request))

    return _View


AdminUserApproveView = _user_action(account_services.approve_user, NoteSerializer, {"note": "note"})
AdminUserRejectView = _user_action(account_services.reject_user, ReasonSerializer, {"reason": "reason"})
AdminUserSuspendView = _user_action(account_services.suspend_user, OptionalReasonSerializer, {"reason": "reason"})
AdminUserReinstateView = _user_action(account_services.reinstate_user, OptionalReasonSerializer, {"reason": "reason"})


# ---- Organizations ----------------------------------------------------------------


class AdminOrganizationCreateSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=OrgType.choices)
    organization = OrganizationInputSerializer()
    profile = ProfileInputSerializer(required=False)
    coverage = CoverageInputSerializer(required=False)


class AdminOrganizationUpdateSerializer(serializers.Serializer):
    organization = OrganizationInputSerializer(required=False)
    profile = ProfileInputSerializer(required=False)
    coverage = CoverageInputSerializer(required=False)


class OrgUserSerializer(serializers.Serializer):
    email = serializers.EmailField()
    display_name = serializers.CharField(required=False, allow_blank=True, default="")


def _get_org(pk):
    org = Organization.objects.filter(pk=pk, deleted_at__isnull=True).first()
    if org is None:
        raise NotFound()
    return org


def org_detail(org, request):
    return {
        **organization_data(org),
        "profile": profile_data(org),
        **coverage_data(org),
        "members": [{**user_summary(m.user), "status": m.user.status, "is_primary_contact": m.is_primary_contact}
                    for m in org.members.select_related("user")],
        "documents": [document_data(d, request) for d in org.verification_documents.select_related("file", "uploaded_by_user")],
    }


class AdminOrganizationListView(APIView):
    permission_classes = ADMIN

    def get(self, request):
        qs = Organization.objects.filter(deleted_at__isnull=True)
        params = request.query_params
        if params.get("type"):
            qs = qs.filter(type=params["type"])
        if params.get("verification_status"):
            qs = qs.filter(verification_status__in=params["verification_status"].split(","))
        if params.get("q"):
            qs = qs.filter(Q(legal_name__icontains=params["q"]) | Q(trade_name__icontains=params["q"]))
        qs = apply_sort(qs, request, {"legal_name": "legal_name", "created_at": "created_at", "id": "id"}, "legal_name")
        return _paginate(self, request, qs, organization_data)

    def post(self, request):
        data = validated(AdminOrganizationCreateSerializer, request.data)
        org = account_services.admin_create_organization(actor=request.user, **data)
        return Response(org_detail(org, request), status=status.HTTP_201_CREATED)


class AdminOrganizationDetailView(APIView):
    permission_classes = ADMIN

    def get(self, request, pk):
        return Response(org_detail(_get_org(pk), request))

    def patch(self, request, pk):
        data = validated(AdminOrganizationUpdateSerializer, request.data)
        org = account_services.admin_update_organization(
            actor=request.user, organization=_get_org(pk), organization_data=data.get("organization"),
            profile=data.get("profile"), coverage=data.get("coverage"),
        )
        return Response(org_detail(org, request))


def _org_action(func, serializer, field_map):
    class _View(APIView):
        permission_classes = ADMIN

        def post(self, request, pk):
            data = validated(serializer, request.data)
            func(actor=request.user, organization=_get_org(pk), **{field_map[k]: v for k, v in data.items() if k in field_map})
            return Response(org_detail(_get_org(pk), request))

    return _View


AdminOrganizationApproveView = _org_action(account_services.approve_organization, NoteSerializer, {"note": "note"})
AdminOrganizationRejectView = _org_action(account_services.reject_organization, ReasonSerializer, {"reason": "reason"})
AdminOrganizationSuspendView = _org_action(account_services.suspend_organization, OptionalReasonSerializer, {"reason": "reason"})
AdminOrganizationReinstateView = _org_action(account_services.reinstate_organization, OptionalReasonSerializer, {"reason": "reason"})


class AdminOrganizationUsersView(APIView):
    permission_classes = ADMIN

    def post(self, request, pk):
        data = validated(OrgUserSerializer, request.data)
        user = account_services.admin_create_org_user(actor=request.user, organization=_get_org(pk), **data)
        return Response(user_admin_row(user), status=status.HTTP_201_CREATED)


def _document_action(approve):
    class _View(APIView):
        permission_classes = ADMIN

        def post(self, request, pk):
            data = validated(NoteSerializer, request.data)
            doc = VerificationDocument.objects.filter(pk=pk).first()
            if doc is None:
                raise NotFound()
            doc = account_services.review_document(actor=request.user, document=doc, approve=approve, note=data["note"] or None)
            return Response(document_data(doc, request))

    return _View


AdminDocumentApproveView = _document_action(True)
AdminDocumentRejectView = _document_action(False)


class AdminAuditLogView(APIView):
    permission_classes = ADMIN

    def get(self, request):
        qs = AuditLog.objects.select_related("actor_user")
        for key in ("entity_type", "entity_id", "port_call_id", "actor_user_id"):
            if request.query_params.get(key):
                qs = qs.filter(**{key: request.query_params[key]})
        if request.query_params.get("action"):
            qs = qs.filter(action__startswith=request.query_params["action"])
        return _paginate(self, request, qs.order_by("-created_at", "-id"), audit_row)


# ---- Master data writes -------------------------------------------------------------


class LocationInput(serializers.Serializer):
    country_code = serializers.CharField(max_length=2)
    name = serializers.CharField(max_length=120)
    region = serializers.CharField(max_length=120, required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)


class PortInput(serializers.Serializer):
    location_id = serializers.IntegerField()
    name = serializers.CharField(max_length=150)
    unlocode = serializers.RegexField(r"^[A-Z]{2}[A-Z0-9]{3}$", required=False, allow_null=True)
    timezone = serializers.CharField(max_length=64)
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    is_active = serializers.BooleanField(required=False)


class ServiceInput(serializers.Serializer):
    code = serializers.RegexField(r"^[A-Z0-9_]{2,40}$")
    name = serializers.CharField(max_length=100)
    description = serializers.CharField(required=False, allow_blank=True)
    is_vendor_service = serializers.BooleanField(required=False)
    sort_order = serializers.IntegerField(required=False)
    is_active = serializers.BooleanField(required=False)


class CargoInput(serializers.Serializer):
    code = serializers.RegexField(r"^[A-Z0-9_]{2,40}$")
    name = serializers.CharField(max_length=100)
    is_active = serializers.BooleanField(required=False)


class CurrencyInput(serializers.Serializer):
    is_active = serializers.BooleanField()


def _fk_fields(data):
    out = dict(data)
    if "country_code" in out:
        out["country_id"] = out.pop("country_code")
    return out


def master_views(model, input_serializer, render, *, lookup="pk"):
    class ListCreate(APIView):
        permission_classes = ADMIN

        @transaction.atomic
        def post(self, request):
            data = _fk_fields(validated(input_serializer, request.data))
            obj = model.objects.create(**data)
            audit(actor=request.user, action=f"{model._meta.db_table}.created", entity=obj, metadata={"data": {k: str(v) for k, v in data.items()}})
            return Response(render(obj), status=status.HTTP_201_CREATED)

    class Detail(APIView):
        permission_classes = ADMIN

        @transaction.atomic
        def patch(self, request, pk):
            obj = model.objects.select_for_update().filter(**{lookup: pk}).first()
            if obj is None:
                raise NotFound()
            data = _fk_fields(validated(input_serializer, request.data, partial=True))
            changes = diff(obj, data)
            obj.save()
            audit(actor=request.user, action=f"{model._meta.db_table}.updated", entity=obj if lookup == "pk" else _CodeEntity(obj),
                  changes=changes, metadata={"key": str(obj.pk)})
            return Response(render(obj))

    return ListCreate, Detail


class _CodeEntity:
    """Audit adapter for string-PK master data (currencies): stores a stable numeric hash id."""

    def __init__(self, obj):
        import zlib

        self._meta = obj._meta
        self.pk = zlib.crc32(str(obj.pk).encode())


AdminLocationCreateView, AdminLocationDetailView = master_views(Location, LocationInput, location_data)
AdminPortCreateView, AdminPortDetailView = master_views(Port, PortInput, port_data)
AdminServiceCreateView, AdminServiceDetailView = master_views(ServiceCategory, ServiceInput, service_data)
AdminCargoCreateView, AdminCargoDetailView = master_views(CargoType, CargoInput, cargo_data)
_, AdminCurrencyDetailView = master_views(Currency, CurrencyInput, currency_data, lookup="code")


def policy_data(p):
    return {"id": p.pk, "request_type": p.request_type, "from_role": p.from_role, "to_role": p.to_role, "is_enabled": p.is_enabled,
            "requires_port_call": p.requires_port_call, "creates_chat_thread": p.creates_chat_thread}


class PolicyInput(serializers.Serializer):
    is_enabled = serializers.BooleanField()


class AdminPolicyListView(APIView):
    permission_classes = ADMIN

    def get(self, request):
        return Response([policy_data(p) for p in RequestRolePolicy.objects.order_by("request_type", "from_role", "to_role")])


class AdminPolicyDetailView(APIView):
    permission_classes = ADMIN

    @transaction.atomic
    def patch(self, request, pk):
        policy = RequestRolePolicy.objects.select_for_update().filter(pk=pk).first()
        if policy is None:
            raise NotFound()
        data = validated(PolicyInput, request.data)
        changes = diff(policy, data)
        policy.save()
        audit(actor=request.user, action="request_policy.updated", entity=policy, changes=changes)
        return Response(policy_data(policy))
