from django.db.models import Prefetch, Q
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.audit import audit
from apps.core.enums import FilePurpose, OrgType, Role, VerificationStatus
from apps.core.exceptions import NotFound
from apps.core.pagination import StandardPagination, apply_sort
from apps.core.permissions import approved
from apps.core.serializers import org_summary
from apps.core.serializers import validated
from apps.documents.services import store_upload

from . import services
from .models import Organization, OrganizationPort, OrganizationService, VerificationDocument
from .serializers import (
    ChooseRoleSerializer,
    CoverageInputSerializer,
    DocumentUploadSerializer,
    OrganizationInputSerializer,
    ProfileInputSerializer,
    agent_row,
    coverage_data,
    document_data,
    me_data,
    onboarding_data,
    organization_data,
    profile_data,
)


class OnboardingPermissionMixin:
    """Auth + onboarding endpoints are exempt from IsApproved (API.md §0)."""

    permission_classes = [IsAuthenticated]


class MeView(OnboardingPermissionMixin, APIView):
    def get(self, request):
        return Response(me_data(request.user))


class ChooseRoleView(OnboardingPermissionMixin, APIView):
    def post(self, request):
        data = validated(ChooseRoleSerializer, request.data)
        user = services.choose_role(user=request.user, **data)
        return Response(me_data(user), status=status.HTTP_201_CREATED)


class LogoutView(OnboardingPermissionMixin, APIView):
    def post(self, request):
        audit(actor=request.user, action="user.logged_out", entity=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class OnboardingView(OnboardingPermissionMixin, APIView):
    def get(self, request):
        return Response(onboarding_data(request.user, request))


class OnboardingOrganizationView(OnboardingPermissionMixin, APIView):
    def put(self, request):
        data = validated(OrganizationInputSerializer, request.data)
        services.update_organization(user=request.user, data=data)
        request.user.refresh_membership()
        return Response(onboarding_data(request.user, request))


class OnboardingProfileView(OnboardingPermissionMixin, APIView):
    def put(self, request):
        data = validated(ProfileInputSerializer, request.data)
        services.update_profile(user=request.user, data=data)
        return Response(onboarding_data(request.user, request))


class OnboardingCoverageView(OnboardingPermissionMixin, APIView):
    def put(self, request):
        data = validated(CoverageInputSerializer, request.data)
        services.update_coverage(user=request.user, **data)
        return Response(onboarding_data(request.user, request))


class OnboardingDocumentsView(OnboardingPermissionMixin, APIView):
    def post(self, request):
        data = validated(DocumentUploadSerializer, request.data)
        stored = store_upload(upload=data["file"], purpose=FilePurpose.VERIFICATION, user=request.user)
        doc = services.add_verification_document(user=request.user, document_type=data["document_type"], title=data.get("title", ""), file=stored)
        return Response(document_data(doc, request), status=status.HTTP_201_CREATED)


class OnboardingDocumentDetailView(OnboardingPermissionMixin, APIView):
    def delete(self, request, pk):
        doc = VerificationDocument.objects.filter(pk=pk, organization_id=request.user.organization_id).first()
        if doc is None:
            raise NotFound()
        services.delete_verification_document(user=request.user, document=doc)
        return Response(status=status.HTTP_204_NO_CONTENT)


class OnboardingSubmitView(OnboardingPermissionMixin, APIView):
    def post(self, request):
        user = services.submit_onboarding(user=request.user)
        return Response(me_data(user))


# ---- Discovery (API.md §5) -------------------------------------------------------


def _approved_agents():
    return (
        Organization.objects.filter(type=OrgType.AGENT, verification_status=VerificationStatus.APPROVED, deleted_at__isnull=True)
        .select_related("agent_profile")
        .prefetch_related(
            Prefetch("service_links", queryset=OrganizationService.objects.select_related("service_category").order_by("service_category__sort_order")),
            Prefetch("port_links", queryset=OrganizationPort.objects.select_related("port").order_by("port__name")),
        )
    )


AGENT_SORTS = {"rating": "agent_profile__rating_avg", "name": "legal_name", "id": "id", "rating_count": "agent_profile__rating_count"}


class AgentListView(APIView):
    permission_classes = approved(Role.OWNER, Role.AGENT, Role.ADMIN)

    def get(self, request):
        qs = _approved_agents()
        params = request.query_params
        if params.get("port_id"):
            qs = qs.filter(port_links__port_id=params["port_id"])
        if params.get("location_id"):
            qs = qs.filter(location_links__location_id=params["location_id"])
        if params.get("service_category_id"):
            qs = qs.filter(service_links__service_category_id=params["service_category_id"])
        if params.get("min_rating"):
            qs = qs.filter(agent_profile__rating_avg__gte=params["min_rating"])
        if params.get("q"):
            qs = qs.filter(Q(legal_name__icontains=params["q"]) | Q(trade_name__icontains=params["q"]))
        qs = apply_sort(qs.distinct(), request, AGENT_SORTS, "-rating")
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([agent_row(org) for org in page])


class AgentDetailView(APIView):
    permission_classes = approved(Role.OWNER, Role.AGENT, Role.ADMIN)

    def get(self, request, pk):
        from apps.ratings.models import Rating

        org = _approved_agents().filter(pk=pk).first()
        if org is None:
            raise NotFound()
        ratings = Rating.objects.filter(ratee_organization=org).select_related("port_call").order_by("-created_at")
        distribution = {str(i): 0 for i in range(1, 6)}
        for score in ratings.values_list("score", flat=True):
            distribution[str(score)] += 1
        return Response({
            **organization_data(org),
            "profile": profile_data(org),
            **coverage_data(org),
            "rating_distribution": distribution,
            "recent_ratings": [
                {"score": r.score, "comment": r.comment, "created_at": r.created_at.isoformat(), "port_call_reference": r.port_call.reference}
                for r in ratings[:10]
            ],
        })


# ---- Merchant discovery for agents (PROGRESS.md C11) ---------------------------------


def merchant_row(org):
    profile = getattr(org, "merchant_profile", None)
    return {
        **org_summary(org),
        "rating_avg": str(profile.rating_avg) if profile else "0.00",
        "rating_count": profile.rating_count if profile else 0,
        "default_currency_code": profile.default_currency_id if profile else None,
        "description": profile.description if profile else "",
        "services": [{"id": s.service_category_id, "code": s.service_category.code, "name": s.service_category.name} for s in org.service_links.all()],
        "ports": [{"id": p.port_id, "name": p.port.name, "unlocode": p.port.unlocode} for p in org.port_links.all()],
    }


MERCHANT_SORTS = {"name": "legal_name", "id": "id", "rating": "merchant_profile__rating_avg"}


class MerchantListView(APIView):
    permission_classes = approved(Role.AGENT, Role.ADMIN)

    def get(self, request):
        qs = (
            Organization.objects.filter(type=OrgType.MERCHANT, verification_status=VerificationStatus.APPROVED, deleted_at__isnull=True)
            .select_related("merchant_profile")
            .prefetch_related(
                Prefetch("service_links", queryset=OrganizationService.objects.select_related("service_category").order_by("service_category__sort_order")),
                Prefetch("port_links", queryset=OrganizationPort.objects.select_related("port").order_by("port__name")),
            )
        )
        params = request.query_params
        if params.get("port_id"):
            qs = qs.filter(port_links__port_id=params["port_id"])
        if params.get("service_category_id"):
            qs = qs.filter(service_links__service_category_id=params["service_category_id"])
        if params.get("q"):
            qs = qs.filter(Q(legal_name__icontains=params["q"]) | Q(trade_name__icontains=params["q"]))
        qs = apply_sort(qs.distinct(), request, MERCHANT_SORTS, "name")
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([merchant_row(org) for org in page])
