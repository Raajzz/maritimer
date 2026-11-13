from django.db.models import Count, OuterRef, Q, Subquery
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.core.enums import Role
from apps.core.exceptions import NotFound, ValidationFailed
from apps.core.pagination import StandardPagination
from apps.core.permissions import approved
from apps.core.serializers import dt, file_ref, org_summary, user_summary, validated
from apps.documents.models import StoredFile

from . import services
from .models import ChatMessage, ChatReadReceipt, ChatThread

PARTICIPANTS = approved(Role.OWNER, Role.AGENT, Role.MERCHANT)


class MessageSerializer(serializers.Serializer):
    body = serializers.CharField(required=False, allow_blank=True, default="", max_length=5000)
    file_id = serializers.IntegerField(required=False, allow_null=True)


class ReadSerializer(serializers.Serializer):
    last_read_message_id = serializers.IntegerField()


def message_data(m, request):
    return {
        "id": m.pk,
        "thread_id": m.thread_id,
        "sender": user_summary(m.sender_user),
        "sender_organization": org_summary(m.sender_organization),
        "body": m.body,
        "file": file_ref(m.file, request),
        "created_at": dt(m.created_at),
    }


def scoped_threads(user):
    return ChatThread.objects.filter(participants__organization_id=user.organization_id).select_related("port_call").distinct()


def get_thread(user, pk):
    thread = scoped_threads(user).filter(pk=pk).first()
    if thread is None:
        raise NotFound()
    return thread


def thread_data(thread, user, request, *, unread=None, last=None):
    participants = [org_summary(p.organization) for p in thread.participants.select_related("organization")]
    if last is None:
        last = thread.messages.select_related("sender_user", "sender_organization", "file").order_by("-id").first()
    if unread is None:
        receipt = ChatReadReceipt.objects.filter(thread=thread, user=user).first()
        after = receipt.last_read_message_id if receipt and receipt.last_read_message_id else 0
        unread = thread.messages.filter(id__gt=after).exclude(sender_user=user).count()
    return {
        "id": thread.pk,
        "kind": thread.kind,
        "subject": thread.subject,
        "port_call": {"id": thread.port_call_id, "reference": thread.port_call.reference, "status": thread.port_call.status},
        "request_id": thread.request_id,
        "participants": participants,
        "last_message": message_data(last, request) if last else None,
        "last_message_at": dt(thread.last_message_at),
        "unread_count": unread,
        "is_closed": thread.is_closed,
    }


class ThreadListView(APIView):
    permission_classes = PARTICIPANTS

    def get(self, request):
        qs = scoped_threads(request.user)
        if request.query_params.get("port_call_id"):
            qs = qs.filter(port_call_id=request.query_params["port_call_id"])
        qs = qs.order_by("-last_message_at", "-id")
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([thread_data(t, request.user, request) for t in page])


class ThreadDetailView(APIView):
    permission_classes = PARTICIPANTS

    def get(self, request, pk):
        return Response(thread_data(get_thread(request.user, pk), request.user, request))


class ThreadMessagesView(APIView):
    permission_classes = PARTICIPANTS

    def get_throttles(self):
        if self.request.method == "POST":
            self.throttle_scope = "chat"
            return [ScopedRateThrottle()]
        return super().get_throttles()

    def get(self, request, pk):
        thread = get_thread(request.user, pk)
        qs = thread.messages.select_related("sender_user", "sender_organization", "file")
        try:
            after_id = int(request.query_params.get("after_id") or 0)
            limit = min(max(int(request.query_params.get("limit") or 50), 1), 200)
        except ValueError as exc:
            raise ValidationFailed("after_id and limit must be integers.") from exc
        if after_id:
            messages = list(qs.filter(id__gt=after_id).order_by("id")[:limit])
        else:
            messages = list(reversed(qs.order_by("-id")[:limit]))  # latest page, ascending
        return Response({"results": [message_data(m, request) for m in messages], "is_closed": thread.is_closed})

    def post(self, request, pk):
        data = validated(MessageSerializer, request.data)
        thread = get_thread(request.user, pk)
        stored = None
        if data.get("file_id"):
            stored = StoredFile.objects.filter(pk=data["file_id"], uploaded_by_user=request.user).first()
            if stored is None:
                raise ValidationFailed("Unknown file.", {"file_id": ["Upload it first."]})
        message = services.post_message(user=request.user, thread=thread, body=data["body"], file=stored)
        message = ChatMessage.objects.select_related("sender_user", "sender_organization", "file").get(pk=message.pk)
        return Response(message_data(message, request), status=status.HTTP_201_CREATED)


class ThreadReadView(APIView):
    permission_classes = PARTICIPANTS

    def post(self, request, pk):
        data = validated(ReadSerializer, request.data)
        receipt = services.mark_read(user=request.user, thread=get_thread(request.user, pk), last_read_message_id=data["last_read_message_id"])
        return Response({"last_read_message_id": receipt.last_read_message_id})


__all__ = ["Count", "OuterRef", "Q", "Subquery"]
