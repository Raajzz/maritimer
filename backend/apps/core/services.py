"""Helpers shared by every app's services.py."""
from django.utils import timezone

from .audit import audit
from .exceptions import Forbidden, ValidationFailed


def lock(instance):
    """Re-read `instance` with SELECT ... FOR UPDATE. Call inside transaction.atomic()."""
    return type(instance).objects.select_for_update().get(pk=instance.pk)


def transition(*, machine, instance, event, actor, action, port_call=None, field="status", metadata=None, extra_updates=None):
    """Validate `event` against `machine`, set the new status, save, and audit. Returns the instance."""
    current = getattr(instance, field)
    target = machine.assert_can(event, current)
    setattr(instance, field, target)
    update_fields = [field]
    if hasattr(instance, "status_changed_at"):
        instance.status_changed_at = timezone.now()
        update_fields.append("status_changed_at")
    for key, value in (extra_updates or {}).items():
        setattr(instance, key, value)
        update_fields.append(key)
    if hasattr(instance, "updated_at"):
        update_fields.append("updated_at")
    instance.save(update_fields=update_fields)
    audit(
        actor=actor,
        action=action,
        entity=instance,
        port_call=port_call,
        from_state=current,
        to_state=target,
        metadata=metadata,
    )
    return instance


def require(condition, message, details=None):
    if not condition:
        raise ValidationFailed(message, details)


def require_permission(condition, message="You do not have permission to perform this action."):
    if not condition:
        raise Forbidden(message)
