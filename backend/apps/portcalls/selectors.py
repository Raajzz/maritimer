"""Object scoping (API.md §0 layer 4). Every non-admin read goes through these filters."""
from django.db.models import Q

from apps.core.enums import RequestStatus, RequestType, Role
from apps.core.exceptions import NotFound

from .models import PortCall


def port_calls_for(user):
    qs = PortCall.objects.select_related(
        "vessel", "port", "port__location", "owner_organization", "agent_organization", "cargo_type"
    )
    if user.role == Role.ADMIN:
        return qs
    org_id = user.organization_id
    if org_id is None:
        return qs.none()
    if user.role == Role.OWNER:
        return qs.filter(owner_organization_id=org_id)
    if user.role == Role.AGENT:
        return qs.filter(agent_organization_id=org_id)
    if user.role == Role.MERCHANT:
        return qs.filter(
            Q(
                requests__request_type=RequestType.VENDOR_SERVICE,
                requests__to_organization_id=org_id,
                requests__status=RequestStatus.ACCEPTED,
            )
            | Q(vendor_invoices__vendor_organization_id=org_id)
        ).distinct()
    return qs.none()


def get_port_call_for(user, pk, *, for_update=False):
    qs = port_calls_for(user)
    if for_update:
        # DISTINCT cannot be combined with FOR UPDATE: check scope first, then lock.
        if not qs.filter(pk=pk).exists():
            raise NotFound()
        return PortCall.objects.select_for_update().get(pk=pk)
    port_call = qs.filter(pk=pk).first()
    if port_call is None:
        raise NotFound()
    return port_call


def party_role(user, port_call) -> str | None:
    """OWNER / AGENT / MERCHANT / ADMIN relative to this port call, or None."""
    if user.role == Role.ADMIN:
        return "ADMIN"
    org_id = user.organization_id
    if org_id is None:
        return None
    if port_call.owner_organization_id == org_id:
        return "OWNER"
    if port_call.agent_organization_id == org_id:
        return "AGENT"
    if user.role == Role.MERCHANT and port_calls_for(user).filter(pk=port_call.pk).exists():
        return "MERCHANT"
    return None


def is_owner_of(user, port_call) -> bool:
    return user.organization_id is not None and port_call.owner_organization_id == user.organization_id


def is_agent_of(user, port_call) -> bool:
    return user.organization_id is not None and port_call.agent_organization_id == user.organization_id
