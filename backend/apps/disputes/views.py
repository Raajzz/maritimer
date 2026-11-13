from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.enums import ResolutionType, Role
from apps.core.exceptions import NotFound, ValidationFailed
from apps.core.pagination import StandardPagination, apply_sort
from apps.core.permissions import approved
from apps.core.serializers import MoneyField, RequiredNoteSerializer, dec, dt, file_ref, money, user_summary, validated
from apps.documents.models import StoredFile
from apps.portcalls.selectors import port_calls_for

from . import services
from .models import Dispute


class OpenDisputeSerializer(serializers.Serializer):
    line_item_id = serializers.IntegerField()
    reason = serializers.CharField()
    disputed_amount = MoneyField(required=False, allow_null=True)


class CommentSerializer(serializers.Serializer):
    body = serializers.CharField(required=False, allow_blank=True, default="")
    file_id = serializers.IntegerField(required=False, allow_null=True)


class ResolveSerializer(serializers.Serializer):
    resolution_type = serializers.ChoiceField(choices=[ResolutionType.EXPLAINED, ResolutionType.ADJUSTED])
    note = serializers.CharField()
    adjusted_local_amount = MoneyField(required=False, allow_null=True)
    mode = serializers.ChoiceField(choices=["EDIT_LINE", "CREDIT_LINE"], required=False, allow_null=True)


class ReopenSerializer(serializers.Serializer):
    body = serializers.CharField(required=False, allow_blank=True, default="")


def dispute_row(d):
    line = d.line_item
    return {
        "id": d.pk,
        "reference": d.reference,
        "port_call_id": d.port_call_id,
        "port_call_reference": d.port_call.reference,
        "status": d.status,
        "line_item_id": line.pk,
        "line_description": line.description,
        "line_amount": money(line.amount, line.account.currency_id),
        "disputed_amount": money(d.disputed_amount, line.account.currency_id),
        "reason": d.reason,
        "resolution_type": d.resolution_type,
        "reopen_count": d.reopen_count,
        "created_at": dt(d.created_at),
        "resolved_at": dt(d.resolved_at),
    }


def dispute_detail(d, request):
    line = d.line_item
    return {
        **dispute_row(d),
        "raised_by": user_summary(d.raised_by_user),
        "resolution_note": d.resolution_note,
        "resolved_by": user_summary(d.resolved_by_user),
        "resolved_in_account_id": d.resolved_in_account_id,
        "fda": {"id": d.resolved_in_account.pk, "version": d.resolved_in_account.version, "status": d.resolved_in_account.status,
                "reference": d.resolved_in_account.reference} if d.resolved_in_account_id else None,
        "adjustment_line_item_id": d.adjustment_line_item_id,
        "line_item": {
            "id": line.pk,
            "account_id": line.account_id,
            "account_version": line.account.version,
            "account_reference": line.account.reference,
            "description": line.description,
            "service_category": line.service_category.name,
            "local_amount": dec(line.local_amount),
            "local_currency_code": line.local_currency_id,
            "fx_rate_applied": dec(line.fx_rate_applied),
            "amount": dec(line.amount),
            "vendor_invoice_id": line.vendor_invoice_id,
        },
        "events": [
            {"id": e.pk, "event_type": e.event_type, "actor": user_summary(e.actor_user), "from_status": e.from_status,
             "to_status": e.to_status, "body": e.body, "file": file_ref(e.file, request), "created_at": dt(e.created_at)}
            for e in d.events.select_related("actor_user", "file")
        ],
    }


def scoped_disputes(user):
    qs = Dispute.objects.select_related("port_call", "line_item", "line_item__account", "line_item__service_category", "raised_by_user", "resolved_by_user")
    if user.role == Role.ADMIN:
        return qs
    if user.role not in (Role.OWNER, Role.AGENT):
        return qs.none()
    return qs.filter(port_call__in=port_calls_for(user).values("pk"))


def get_dispute(user, pk):
    d = scoped_disputes(user).filter(pk=pk).first()
    if d is None:
        raise NotFound()
    return d


PARTIES = approved(Role.OWNER, Role.AGENT, Role.ADMIN)


class DisputeListView(APIView):
    permission_classes = PARTIES

    def get(self, request):
        qs = scoped_disputes(request.user)
        params = request.query_params
        if params.get("port_call_id"):
            qs = qs.filter(port_call_id=params["port_call_id"])
        if params.get("status"):
            qs = qs.filter(status__in=params["status"].split(","))
        qs = apply_sort(qs, request, {"created_at": "created_at", "status": "status", "id": "id"}, "-created_at")
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([dispute_row(d) for d in page])

    def post(self, request):
        if request.user.role != Role.OWNER:
            raise NotFound()
        data = validated(OpenDisputeSerializer, request.data)
        d = services.open_dispute(actor=request.user, **data)
        return Response(dispute_detail(get_dispute(request.user, d.pk), request), status=status.HTTP_201_CREATED)


class DisputeDetailView(APIView):
    permission_classes = PARTIES

    def get(self, request, pk):
        return Response(dispute_detail(get_dispute(request.user, pk), request))


class DisputeCommentView(APIView):
    permission_classes = approved(Role.OWNER, Role.AGENT)

    def post(self, request, pk):
        data = validated(CommentSerializer, request.data)
        stored = None
        if data.get("file_id"):
            stored = StoredFile.objects.filter(pk=data["file_id"], uploaded_by_user=request.user).first()
            if stored is None:
                raise ValidationFailed("Unknown file.", {"file_id": ["Upload it first."]})
        services.comment(actor=request.user, dispute=get_dispute(request.user, pk), body=data["body"], file=stored)
        return Response(dispute_detail(get_dispute(request.user, pk), request), status=status.HTTP_201_CREATED)


def _dispute_action(roles, func, serializer=None, rename=None):
    class _View(APIView):
        permission_classes = approved(*roles)

        def post(self, request, pk):
            kwargs = dict(validated(serializer, request.data)) if serializer else {}
            for old, new in (rename or {}).items():
                if old in kwargs:
                    kwargs[new] = kwargs.pop(old)
            func(actor=request.user, dispute=get_dispute(request.user, pk), **kwargs)
            return Response(dispute_detail(get_dispute(request.user, pk), request))

    return _View


DisputeAcknowledgeView = _dispute_action([Role.AGENT], services.acknowledge)
DisputeResolveView = _dispute_action([Role.AGENT], services.resolve, ResolveSerializer)
DisputeRejectView = _dispute_action([Role.AGENT], services.reject, RequiredNoteSerializer)
DisputeWithdrawView = _dispute_action([Role.OWNER], services.withdraw)
DisputeReopenView = _dispute_action([Role.OWNER], services.reopen, ReopenSerializer)
