"""Audit logging. Call inside the service transaction so the entry commits atomically with the change."""
from decimal import Decimal

from .middleware import current_ip


def _jsonable(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def audit(*, actor, action, entity, port_call=None, from_state=None, to_state=None, changes=None, metadata=None):
    from .models import AuditLog

    organization = None
    role = None
    if actor is not None:
        role = actor.role
        organization = actor.organization
    if port_call is None and entity.__class__.__name__ == "PortCall":
        port_call = entity
    return AuditLog.objects.create(
        actor_user=actor,
        actor_role=role,
        actor_organization=organization,
        action=action,
        entity_type=entity._meta.db_table,
        entity_id=entity.pk,
        port_call=port_call,
        from_state=str(from_state) if from_state is not None else None,
        to_state=str(to_state) if to_state is not None else None,
        changes=_jsonable(changes or {}),
        metadata=_jsonable(metadata or {}),
        ip_address=current_ip(),
    )


def diff(instance, data: dict) -> dict:
    """Apply `data` to instance attributes and return {field: {from, to}} for changed fields."""
    changes = {}
    for field, new in data.items():
        old = getattr(instance, field)
        if old != new:
            changes[field] = {"from": _jsonable(old), "to": _jsonable(new)}
            setattr(instance, field, new)
    return changes
