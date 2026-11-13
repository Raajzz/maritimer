from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.enums import ThreadKind, check_in
from apps.core.models import TimeStampedModel


class ChatThread(TimeStampedModel):
    kind = models.CharField(max_length=16, choices=ThreadKind.choices)
    port_call = models.ForeignKey("portcalls.PortCall", on_delete=models.PROTECT, related_name="chat_threads")
    request = models.ForeignKey("requests.Request", null=True, blank=True, on_delete=models.PROTECT, related_name="chat_threads")
    subject = models.CharField(max_length=200)
    last_message_at = models.DateTimeField(null=True, blank=True)  # denormalized (D16)
    is_closed = models.BooleanField(default=False)

    class Meta:
        db_table = "chat_threads"
        constraints = [
            models.CheckConstraint(condition=check_in("kind", ThreadKind), name="thread_kind_chk"),
            models.UniqueConstraint(fields=["port_call"], condition=Q(kind=ThreadKind.PORT_CALL), name="thread_one_per_call_uniq"),
            models.UniqueConstraint(fields=["request"], condition=Q(kind=ThreadKind.VENDOR_SERVICE), name="thread_one_per_request_uniq"),
            models.CheckConstraint(
                condition=Q(kind=ThreadKind.VENDOR_SERVICE, request__isnull=False)
                | (~Q(kind=ThreadKind.VENDOR_SERVICE) & Q(request__isnull=True)),
                name="thread_vendor_request_chk",
            ),
        ]


class ChatParticipant(TimeStampedModel):
    thread = models.ForeignKey(ChatThread, on_delete=models.CASCADE, related_name="participants")
    organization = models.ForeignKey("accounts.Organization", on_delete=models.PROTECT, related_name="+")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "chat_participants"
        constraints = [models.UniqueConstraint(fields=["thread", "organization"], name="thread_participant_uniq")]


class ChatMessage(models.Model):
    thread = models.ForeignKey(ChatThread, on_delete=models.PROTECT, related_name="messages")
    sender_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    sender_organization = models.ForeignKey("accounts.Organization", on_delete=models.PROTECT, related_name="+")
    body = models.TextField(default="", blank=True)
    file = models.ForeignKey("documents.StoredFile", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "chat_messages"
        ordering = ["id"]
        indexes = [models.Index(fields=["thread", "id"], name="chat_message_thread_idx")]
        constraints = [
            models.CheckConstraint(condition=~Q(body="") | Q(file__isnull=False), name="chat_message_nonempty_chk"),
        ]


class ChatReadReceipt(models.Model):
    thread = models.ForeignKey(ChatThread, on_delete=models.CASCADE, related_name="read_receipts")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    last_read_message = models.ForeignKey(ChatMessage, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "chat_read_receipts"
        constraints = [models.UniqueConstraint(fields=["thread", "user"], name="read_receipt_uniq")]

