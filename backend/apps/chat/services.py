from django.db import transaction
from django.utils import timezone

from apps.core.enums import OrgType, ThreadKind
from apps.core.exceptions import Forbidden, InvalidTransition, ValidationFailed

from .models import ChatMessage, ChatParticipant, ChatReadReceipt, ChatThread


def create_thread(*, kind, port_call, organizations, subject, request=None):
    """Only called from request acceptance. Owner and merchant orgs never share a thread."""
    types = {org.type for org in organizations}
    if OrgType.OWNER in types and OrgType.MERCHANT in types:
        raise ValidationFailed("Owners and merchants cannot share a chat thread.")
    thread = ChatThread.objects.create(kind=kind, port_call=port_call, request=request if kind == ThreadKind.VENDOR_SERVICE else None,
                                       subject=subject[:200])
    for org in organizations:
        ChatParticipant.objects.create(thread=thread, organization=org)
    return thread


def is_participant(user, thread) -> bool:
    org_id = user.organization_id
    return org_id is not None and thread.participants.filter(organization_id=org_id).exists()


@transaction.atomic
def post_message(*, user, thread, body="", file=None):
    if not is_participant(user, thread):
        raise Forbidden()
    thread = ChatThread.objects.select_for_update().get(pk=thread.pk)
    if thread.is_closed:
        raise InvalidTransition("This conversation is closed.")
    body = (body or "").strip()
    if not body and file is None:
        raise ValidationFailed("Message cannot be empty.", {"body": ["Required."]})
    if len(body) > 5000:
        raise ValidationFailed("Message is too long.", {"body": ["Max 5000 characters."]})
    message = ChatMessage.objects.create(thread=thread, sender_user=user, sender_organization_id=user.organization_id, body=body, file=file)
    thread.last_message_at = message.created_at
    thread.save(update_fields=["last_message_at", "updated_at"])
    ChatReadReceipt.objects.update_or_create(thread=thread, user=user, defaults={"last_read_message": message})
    return message


def mark_read(*, user, thread, last_read_message_id):
    if not is_participant(user, thread):
        raise Forbidden()
    message = thread.messages.filter(pk=last_read_message_id).first()
    if message is None:
        raise ValidationFailed("Unknown message.", {"last_read_message_id": ["Not in this thread."]})
    receipt, _ = ChatReadReceipt.objects.get_or_create(thread=thread, user=user)
    if receipt.last_read_message_id is None or receipt.last_read_message_id < message.pk:
        receipt.last_read_message = message
        receipt.save()
    return receipt


def close_threads_for(port_call):
    ChatThread.objects.filter(port_call=port_call, is_closed=False).update(is_closed=True, updated_at=timezone.now())
