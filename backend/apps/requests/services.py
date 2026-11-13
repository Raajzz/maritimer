"""Generic request lifecycle (STATE_MACHINES.md §2)."""
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Organization
from apps.chat.services import create_thread
from apps.core.audit import audit
from apps.core.enums import PORT_CALL_FROZEN, RequestStatus, RequestType, ThreadKind
from apps.core.exceptions import Forbidden, NotFound, ValidationFailed
from apps.core.money import to_decimal
from apps.core.references import next_reference
from apps.core.services import lock, require, transition
from apps.masterdata.models import CargoType, Port, ServiceCategory
from apps.portcalls.models import PortCall
from apps.vessels.models import Vessel

from .models import PortCallRequestDetail, Request, RequestService
from .policy import assert_allowed
from .transitions import REQUEST_MACHINE


def _services(request, services):
    seen = set()
    for item in services or []:
        category_id = item.get("service_category_id")
        category = ServiceCategory.objects.filter(pk=category_id, is_active=True).first()
        require(category is not None, "Unknown service category.", {"services": [f"Invalid service_category_id {category_id}."]})
        require(category_id not in seen, "Duplicate service in request.", {"services": [f"Duplicate {category_id}."]})
        seen.add(category_id)
        quantity = item.get("quantity")
        RequestService.objects.create(
            request=request,
            service_category=category,
            quantity=to_decimal(quantity) if quantity not in (None, "") else None,
            unit=item.get("unit") or "",
            notes=item.get("notes") or "",
        )


@transaction.atomic
def create_request(*, actor, data):
    request_type = data.get("request_type")
    require(request_type in RequestType.values, "Invalid request type.", {"request_type": ["Invalid choice."]})
    from_org = actor.organization
    require(from_org is not None and from_org.is_approved, "Your organization is not approved.")
    to_org = Organization.objects.filter(pk=data.get("to_organization_id"), deleted_at__isnull=True).first()
    if to_org is None or not to_org.is_approved:
        raise NotFound("Recipient organization not found.")
    require(to_org.pk != from_org.pk, "You cannot send a request to your own organization.")
    policy = assert_allowed(request_type, actor.role, to_org.type)

    port_call = None
    if policy.requires_port_call or request_type == RequestType.VENDOR_SERVICE:
        port_call = PortCall.objects.filter(pk=data.get("port_call_id"), agent_organization_id=from_org.pk).first()
        if port_call is None:
            raise NotFound("Port call not found.")
        require(port_call.status not in PORT_CALL_FROZEN, "Vendor services can no longer be requested for this port call.",
                {"port_call_id": [f"Port call is {port_call.status}."]})

    detail = None
    if request_type == RequestType.PORT_CALL:
        detail = data.get("details") or {}
        vessel = Vessel.objects.filter(pk=detail.get("vessel_id"), owner_organization_id=from_org.pk, deleted_at__isnull=True).first()
        require(vessel is not None, "Vessel not found in your fleet.", {"details.vessel_id": ["Invalid."]})
        port = Port.objects.filter(pk=detail.get("port_id"), is_active=True).first()
        require(port is not None, "Unknown or inactive port.", {"details.port_id": ["Invalid."]})
        cargo = CargoType.objects.filter(pk=detail.get("cargo_type_id"), is_active=True).first()
        require(cargo is not None, "Unknown cargo type.", {"details.cargo_type_id": ["Invalid."]})
        eta, etd = detail.get("eta"), detail.get("etd")
        require(eta and etd and etd > eta, "ETD must be after ETA.", {"details.etd": ["Must be after ETA."]})
        detail = {**detail, "vessel": vessel, "port": port, "cargo_type": cargo}

    request = Request.objects.create(
        reference=next_reference("REQ"),
        request_type=request_type,
        from_user=actor,
        from_organization=from_org,
        from_role=actor.role,
        to_organization=to_org,
        to_role=to_org.type,
        port_call=port_call,
        subject=(data.get("subject") or "")[:200],
        message=data.get("message") or "",
        payload=data.get("payload") or {},
        expires_at=data.get("expires_at"),
    )
    if detail is not None:
        quantity = detail.get("cargo_quantity")
        PortCallRequestDetail.objects.create(
            request=request,
            vessel=detail["vessel"],
            port=detail["port"],
            eta=detail["eta"],
            etd=detail["etd"],
            cargo_type=detail["cargo_type"],
            cargo_description=detail.get("cargo_description") or "",
            cargo_quantity=to_decimal(quantity) if quantity not in (None, "") else None,
            cargo_unit=detail.get("cargo_unit") or "",
        )
        port_served = to_org.port_links.filter(port=detail["port"]).exists()
    else:
        port_served = True
    _services(request, data.get("services"))
    audit(
        actor=actor,
        action="request.created",
        entity=request,
        port_call=port_call,
        to_state=request.status,
        metadata={"request_type": request_type, "to_organization_id": to_org.pk, "port_served_by_recipient": port_served},
    )
    return request


def _require_recipient(actor, request):
    if actor.organization_id != request.to_organization_id:
        raise Forbidden("Only the recipient can respond to this request.")


@transaction.atomic
def accept_request(*, actor, request, note=""):
    request = lock(request)
    _require_recipient(actor, request)
    from_org = request.from_organization
    if not from_org.is_approved:
        raise ValidationFailed("The requesting organization is no longer approved.")
    now = timezone.now()
    port_call = request.port_call
    if request.request_type == RequestType.PORT_CALL:
        detail = request.port_call_detail
        port_call = PortCall.objects.create(
            reference=next_reference("PC"),
            request=request,
            owner_organization=from_org,
            agent_organization=request.to_organization,
            vessel=detail.vessel,
            port=detail.port,
            cargo_type=detail.cargo_type,
            eta=detail.eta,
            etd=detail.etd,
            notes=request.message,
        )
    else:
        port_call = PortCall.objects.select_for_update().get(pk=request.port_call_id)
        require(port_call.status not in PORT_CALL_FROZEN, "This port call no longer accepts vendor services.")

    transition(
        machine=REQUEST_MACHINE, instance=request, event="accept", actor=actor, action="request.accepted", port_call=port_call,
        extra_updates={"to_user": actor, "responded_at": now, "response_note": note or "", "port_call": port_call},
    )
    if request.request_type == RequestType.PORT_CALL:
        audit(actor=actor, action="port_call.created", entity=port_call, to_state=port_call.status,
              metadata={"request_id": request.pk, "reference": port_call.reference})
        thread = create_thread(
            kind=ThreadKind.PORT_CALL, port_call=port_call, organizations=[from_org, request.to_organization],
            subject=f"{port_call.reference} · {port_call.vessel.name} at {port_call.port.name}",
        )
    else:
        thread = create_thread(
            kind=ThreadKind.VENDOR_SERVICE, port_call=port_call, request=request,
            organizations=[from_org, request.to_organization],
            subject=f"{request.reference} · {request.subject or 'Vendor service'}",
        )
    return request, port_call, thread


@transaction.atomic
def decline_request(*, actor, request, note=""):
    request = lock(request)
    _require_recipient(actor, request)
    return transition(
        machine=REQUEST_MACHINE, instance=request, event="decline", actor=actor, action="request.declined", port_call=request.port_call,
        extra_updates={"to_user": actor, "responded_at": timezone.now(), "response_note": note or ""},
    )


@transaction.atomic
def withdraw_request(*, actor, request, system=False):
    request = lock(request)
    if not system and actor.organization_id != request.from_organization_id:
        raise Forbidden("Only the sender can withdraw this request.")
    return transition(machine=REQUEST_MACHINE, instance=request, event="withdraw", actor=actor, action="request.withdrawn",
                      port_call=request.port_call, metadata={"system": system})


@transaction.atomic
def expire_due_requests(now=None):
    now = now or timezone.now()
    expired = 0
    for request in Request.objects.select_for_update().filter(status=RequestStatus.PENDING, expires_at__lt=now):
        transition(machine=REQUEST_MACHINE, instance=request, event="expire", actor=None, action="request.expired", port_call=request.port_call)
        expired += 1
    return expired
