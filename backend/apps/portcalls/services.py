"""Port call lifecycle (STATE_MACHINES.md §3). PDA/FDA/payment/dispute services move the port call
through `set_status`, so every port-call transition is validated against one table."""
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.core.audit import audit, diff
from apps.core.enums import (
    DISPUTE_LIVE,
    AccountKind,
    AccountStatus,
    PaymentKind,
    PaymentStatus,
    PortCallStatus,
    RequestStatus,
    RequestType,
    Role,
)
from apps.core.exceptions import Forbidden, ValidationFailed
from apps.core.services import require, transition

from .models import PortCall
from .selectors import is_agent_of, is_owner_of
from .transitions import AGENT_EDIT_BLOCKED, OWNER_CANCELLABLE, PORT_CALL_MACHINE


def set_status(*, port_call, event, actor, action, metadata=None, extra_updates=None):
    """port_call must already be locked by the caller."""
    return transition(
        machine=PORT_CALL_MACHINE, instance=port_call, event=event, actor=actor, action=action,
        metadata=metadata, extra_updates=extra_updates,
    )


def lock_port_call(port_call):
    return PortCall.objects.select_for_update().get(pk=port_call.pk)


def require_agent(actor, port_call):
    if not is_agent_of(actor, port_call):
        raise Forbidden("Only this port call's agent can do that.")


def require_owner(actor, port_call):
    if not is_owner_of(actor, port_call):
        raise Forbidden("Only this port call's owner can do that.")


def has_live_disputes(port_call) -> bool:
    from apps.disputes.models import Dispute

    return Dispute.objects.filter(port_call=port_call, status__in=DISPUTE_LIVE).exists()


def confirmed_advance_exists(port_call) -> bool:
    from apps.payments.models import Payment

    return Payment.objects.filter(port_call=port_call, kind=PaymentKind.ADVANCE, status=PaymentStatus.CONFIRMED).exists()


@transaction.atomic
def update_port_call(*, actor, port_call, data):
    port_call = lock_port_call(port_call)
    require_agent(actor, port_call)
    require(port_call.status not in AGENT_EDIT_BLOCKED, f"Port call is {port_call.status} and can no longer be edited.")
    values = {k: data[k] for k in ("eta", "etd", "berth", "notes") if k in data}
    eta, etd = values.get("eta", port_call.eta), values.get("etd", port_call.etd)
    require(etd > eta, "ETD must be after ETA.", {"etd": ["Must be after ETA."]})
    changes = diff(port_call, values)
    port_call.save()
    if changes:
        audit(actor=actor, action="port_call.updated", entity=port_call, changes=changes)
    return port_call


@transaction.atomic
def arrive(*, actor, port_call, ata):
    port_call = lock_port_call(port_call)
    require_agent(actor, port_call)
    require(ata is not None, "Actual time of arrival is required.", {"ata": ["Required."]})
    advance_missing = not confirmed_advance_exists(port_call)
    return set_status(
        port_call=port_call, event="arrive", actor=actor, action="port_call.arrived",
        metadata={"ata": ata, "advance_missing": advance_missing}, extra_updates={"ata": ata},
    )


@transaction.atomic
def depart(*, actor, port_call, atd):
    port_call = lock_port_call(port_call)
    require_agent(actor, port_call)
    require(atd is not None, "Actual time of departure is required.", {"atd": ["Required."]})
    require(atd >= port_call.ata, "Departure must be after arrival.", {"atd": ["Must be ≥ ATA."]})
    return set_status(port_call=port_call, event="depart", actor=actor, action="port_call.departed",
                      metadata={"atd": atd}, extra_updates={"atd": atd})


@transaction.atomic
def cancel(*, actor, port_call, reason):
    from apps.chat.services import close_threads_for
    from apps.disbursements.models import DisbursementAccount
    from apps.disbursements.transitions import PDA_MACHINE
    from apps.requests.models import Request
    from apps.requests.services import withdraw_request

    require(reason, "A reason is required.", {"reason": ["Required."]})
    port_call = lock_port_call(port_call)
    if actor.role == Role.ADMIN:
        pass
    elif is_agent_of(actor, port_call):
        pass
    elif is_owner_of(actor, port_call):
        if port_call.status not in OWNER_CANCELLABLE:
            raise Forbidden("Owners can cancel only before the PDA is approved.")
    else:
        raise Forbidden()
    had_advance = confirmed_advance_exists(port_call)
    set_status(port_call=port_call, event="cancel", actor=actor, action="port_call.cancelled",
               metadata={"reason": reason, "confirmed_advance_needs_refund": had_advance},
               extra_updates={"cancelled_reason": reason})
    for pda in DisbursementAccount.objects.select_for_update().filter(
        port_call=port_call, kind=AccountKind.PDA, is_current=True, status__in=[AccountStatus.DRAFT, AccountStatus.ISSUED, AccountStatus.APPROVED]
    ):
        transition(machine=PDA_MACHINE, instance=pda, event="void", actor=actor, action="pda.voided", port_call=port_call)
    for request in Request.objects.filter(port_call=port_call, request_type=RequestType.VENDOR_SERVICE, status=RequestStatus.PENDING):
        withdraw_request(actor=actor, request=request, system=True)
    close_threads_for(port_call)
    return port_call


@transaction.atomic
def close(*, actor, port_call):
    from apps.accounts.models import AgentProfile
    from apps.chat.services import close_threads_for

    port_call = lock_port_call(port_call)
    require_agent(actor, port_call)
    set_status(port_call=port_call, event="close", actor=actor, action="port_call.closed", extra_updates={"closed_at": timezone.now()})
    AgentProfile.objects.filter(organization_id=port_call.agent_organization_id).update(completed_port_calls=F("completed_port_calls") + 1)
    close_threads_for(port_call)
    return port_call


def recompute_after_dispute_change(*, port_call, actor):
    """Idempotent: DISPUTED → FDA_ISSUED once no live dispute remains; FDA_ISSUED → DISPUTED if one exists."""
    live = has_live_disputes(port_call)
    if port_call.status == PortCallStatus.DISPUTED and not live:
        set_status(port_call=port_call, event="disputes_cleared", actor=actor, action="port_call.disputes_cleared")
    elif port_call.status == PortCallStatus.FDA_ISSUED and live:
        set_status(port_call=port_call, event="dispute_open", actor=actor, action="port_call.disputed")
    return port_call


def ensure_mutable_for_vendor_work(port_call):
    if port_call.status in (PortCallStatus.FDA_FINAL, PortCallStatus.SETTLED, PortCallStatus.CLOSED, PortCallStatus.CANCELLED):
        raise ValidationFailed(f"Port call is {port_call.status}.")
