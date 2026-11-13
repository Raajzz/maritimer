from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.enums import Role
from apps.core.pagination import StandardPagination
from apps.core.permissions import approved
from apps.core.serializers import dt, org_summary, validated
from apps.portcalls.selectors import get_port_call_for

from . import services
from .models import Rating


class RatingInputSerializer(serializers.Serializer):
    ratee_organization_id = serializers.IntegerField()
    score = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(required=False, allow_blank=True, default="")
    vendor_request_id = serializers.IntegerField(required=False, allow_null=True)


def rating_data(r, *, public=False):
    data = {
        "id": r.pk,
        "score": r.score,
        "comment": r.comment,
        "ratee": org_summary(r.ratee_organization),
        "port_call_reference": r.port_call.reference,
        "created_at": dt(r.created_at),
    }
    if not public:
        data["rater"] = org_summary(r.rater_organization)
        data["port_call_id"] = r.port_call_id
    return data


class PortCallRatingsView(APIView):
    permission_classes = approved(Role.OWNER, Role.AGENT, Role.ADMIN)

    def get(self, request, pk):
        pc = get_port_call_for(request.user, pk)
        qs = Rating.objects.filter(port_call=pc).select_related("ratee_organization", "rater_organization", "port_call")
        return Response([rating_data(r) for r in qs])

    def post(self, request, pk):
        data = validated(RatingInputSerializer, request.data)
        pc = get_port_call_for(request.user, pk)
        rating = services.rate(actor=request.user, port_call=pc, **data)
        return Response(rating_data(rating), status=status.HTTP_201_CREATED)


class OrganizationRatingsView(APIView):
    def get(self, request, pk):
        qs = Rating.objects.filter(ratee_organization_id=pk).select_related("ratee_organization", "port_call").order_by("-created_at")
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([rating_data(r, public=True) for r in page])
