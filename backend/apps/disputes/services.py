"""Disputes on FDA line items (STATE_MACHINES.md §8)."""
from django.db import transaction
from django.utils import timezone

from apps.core.audit import audit
from apps.core.enums import (
    DISPUTE_LIVE,
    AccountKind,
    AccountStatus,
    DisputeEventType,
    DisputeStatus,
    PortCallStatus,
    ResolutionType,
)
from apps.core.exceptions import Forbidden, InvalidTransition, ValidationFailed
from apps.core.money import convert, round_money, to_decimal
from apps.core.references import next_reference
from apps.core.services import lock, require
from apps.disbursements.models import DisbursementLineItem
from apps.disbursements.services import _recompute_total, current_account, revise
from apps.portcalls.selectors import is_agent_of, is_owner_of
from apps.portcalls.services import lock_port_call, recompute_after_dispute_change, set_status

from .models import Dispute, DisputeEvent
from .transitions import DISPUTE_MACHINE


def _event(dispute, actor, event_type, *, from_status=None, to_status=None, body="", file=None):
    return DisputeEvent.objects.create(
        dispute=dispute, actor_user=actor, event_type=event_type, from_status=from_status, to_status=to_status, body=body or "", file=file
    )


def _change(dispute, actor, event, *, body="", extra=None, action=None, port_call):
    previous = dispute.status
    target = DISPUTE_MACHINE.assert_can(event, previous)
    dispute.status = target
    for key, value in (extra or {}).items():
        setattr(dispute, key, value)
    dispute.save()
    _event(dispute, actor, DisputeEventType.REOPENED if event == "reopen" else DisputeEventType.STATUS_CHANGED,
           from_status=previous, to_status=target, body=body)
    audit(actor=actor, action=action or f"dispute.{event}", entity=dispute, port_call=port_call, from_state=previous, to_state=target,
          metadata={"note": body} if body else None)
    return dispute


def _close_extra(actor, resolution_type, note):
    return {"resolution_type": resolution_type, "resolution_note": note or "", "resolved_by_user": actor, "resolved_at": timezone.now()}


@transaction.atomic
def open_dispute(*, actor, line_item_id, reason, disputed_amount=None):
    line = DisbursementLineItem.objects.select_related("account", "account__port_call").filter(pk=line_item_id).first()
    if line is None or not is_owner_of(actor, line.account.port_call):
        raise ValidationFailed("Line item not found.", {"line_item_id": ["Invalid."]})
    port_call = lock_port_call(line.account.port_call)
    require(reason and reason.strip(), "Explain what you are disputing.", {"reason": ["Required."]})
    account = line.account
    current = current_account(port_call, AccountKind.FDA)
    if account.kind != AccountKind.FDA or current is None or current.pk != account.pk or account.status != AccountStatus.ISSUED:
        raise InvalidTransition("Only lines of the current issued FDA can be disputed.")
    if port_call.status not in (PortCallStatus.FDA_ISSUED, PortCallStatus.DISPUTED):
        raise InvalidTransition(f"Disputes cannot be opened while the port call is {port_call.status}.")
    if Dispute.objects.filter(line_item=line, status__in=DISPUTE_LIVE).exists():
        raise InvalidTransition("This line already has an open dispute.")
    dispute = Dispute.objects.create(
        reference=next_reference("DSP"),
        port_call=port_call,
        line_item=line,
        raised_by_user=actor,
        raised_by_organization_id=actor.organization_id,
        reason=reason.strip(),
        disputed_amount=round_money(to_decimal(disputed_amount), account.currency_id) if disputed_amount not in (None, "") else None,
    )
    _event(dispute, actor, DisputeEventType.OPENED, to_status=dispute.status, body=dispute.reason)
    audit(actor=actor, action="dispute.opened", entity=dispute, port_call=port_call, to_state=dispute.status,
          metadata={"line_item_id": line.pk, "line_amount": line.amount, "disputed_amount": dispute.disputed_amount})
    if port_call.status == PortCallStatus.FDA_ISSUED:
        set_status(port_call=port_call, event="dispute_open", actor=actor, action="port_call.disputed", metadata={"dispute": dispute.reference})
    return dispute


def _party_check(actor, dispute, *, owner=False, agent=False):
    port_call = dispute.port_call
    if owner and is_owner_of(actor, port_call):
        return "OWNER"
    if agent and is_agent_of(actor, port_call):
        return "AGENT"
    raise Forbidden()


@transaction.atomic
def comment(*, actor, dispute, body, file=None):
    _party_check(actor, dispute, owner=True, agent=True)
    dispute = lock(dispute)
    if dispute.status not in DISPUTE_LIVE:
        raise InvalidTransition("Comments are closed on this dispute.")
    require((body and body.strip()) or file, "Comment cannot be empty.", {"body": ["Required."]})
    event = _event(dispute, actor, DisputeEventType.COMMENT, body=(body or "").strip(), file=file)
    audit(actor=actor, action="dispute.commented", entity=dispute, port_call=dispute.port_call, metadata={"event_id": event.pk})
    return event


@transaction.atomic
def acknowledge(*, actor, dispute):
    _party_check(actor, dispute, agent=True)
    port_call = lock_port_call(dispute.port_call)
    dispute = lock(dispute)
    return _change(dispute, actor, "acknowledge", action="dispute.acknowledged", port_call=port_call)


def _find_descendant_line(draft, line):
    """The line in `draft` that descends (via supersedes_line_item) from `line`."""
    for candidate in draft.line_items.all():
        cursor = candidate
        while cursor is not None:
            if cursor.pk == line.pk:
                return candidate
            cursor = cursor.supersedes_line_item
    return None


@transaction.atomic
def resolve(*, actor, dispute, resolution_type, note, adjusted_local_amount=None, mode=None):
    _party_check(actor, dispute, agent=True)
    port_call = lock_port_call(dispute.port_call)
    dispute = lock(dispute)
    require(resolution_type in (ResolutionType.EXPLAINED, ResolutionType.ADJUSTED), "resolution_type must be EXPLAINED or ADJUSTED.")
    require(note and note.strip(), "A resolution note is required.", {"note": ["Required."]})
    DISPUTE_MACHINE.assert_can("resolve", dispute.status)
    extra = _close_extra(actor, resolution_type, note.strip())

    if resolution_type == ResolutionType.ADJUSTED:
        require(adjusted_local_amount not in (None, ""), "adjusted_local_amount is required for an adjustment.", {"adjusted_local_amount": ["Required."]})
        if port_call.status in (PortCallStatus.FDA_FINAL, PortCallStatus.SETTLED, PortCallStatus.CLOSED):
            raise InvalidTransition("The FDA is final; it can no longer be adjusted.")
        current = current_account(port_call, AccountKind.FDA)
        if current.status == AccountStatus.ISSUED:
            draft = revise(actor=actor, account=current, port_call=port_call)
        elif current.status == AccountStatus.DRAFT:
            draft = current
        else:
            raise InvalidTransition(f"The current FDA is {current.status}; it cannot be adjusted.")
        original = dispute.line_item
        target = _find_descendant_line(draft, original)
        require(target is not None, "The disputed line no longer exists in the current FDA draft.")
        new_local = round_money(to_decimal(adjusted_local_amount), target.local_currency_id)
        require(new_local >= 0, "Adjusted amount must not be negative.")
        mode = mode or ("CREDIT_LINE" if target.vendor_invoice_id else "EDIT_LINE")
        require(mode in ("EDIT_LINE", "CREDIT_LINE"), "mode must be EDIT_LINE or CREDIT_LINE.")
        if mode == "EDIT_LINE":
            require(target.vendor_invoice_id is None, "Invoice-backed lines carry the invoice total; use CREDIT_LINE.", {"mode": ["Use CREDIT_LINE."]})
            before = target.local_amount
            target.local_amount = new_local
            target.amount = convert(new_local, target.fx_rate_applied, draft.currency_id)
            target.notes = (target.notes + f"\nAdjusted from {before} by dispute {dispute.reference}.").strip()
            target.save()
            adjustment_line = target
        else:
            delta = new_local - target.local_amount
            require(delta != 0, "The adjusted amount equals the current amount.")
            next_no = (draft.line_items.order_by("-line_no").values_list("line_no", flat=True).first() or 0) + 1
            adjustment_line = DisbursementLineItem.objects.create(
                account=draft,
                line_no=next_no,
                service_category_id=target.service_category_id,
                description=f"Adjustment: {target.description}"[:300],
                vendor_organization_id=target.vendor_organization_id,
                quantity=1,
                unit="lot",
                local_amount=delta,
                local_currency_id=target.local_currency_id,
                fx_rate_id=target.fx_rate_id,
                fx_rate_applied=target.fx_rate_applied,
                amount=convert(delta, target.fx_rate_applied, draft.currency_id),
                pda_line_item_id=target.pda_line_item_id,
                is_adjustment=True,
                source_dispute=dispute,
                notes=f"Dispute {dispute.reference}",
            )
        _recompute_total(draft)
        extra.update(resolved_in_account=draft, adjustment_line_item=adjustment_line)
        _event(dispute, actor, DisputeEventType.ADJUSTMENT_PROPOSED,
               body=f"Line adjusted to {new_local} {target.local_currency_id} in {draft.reference} ({mode}).")
        audit(actor=actor, action="fda.adjusted", entity=draft, port_call=port_call,
              metadata={"dispute": dispute.reference, "mode": mode, "line_id": adjustment_line.pk, "new_local_amount": new_local,
                        "new_total": draft.total_amount})

    _change(dispute, actor, "resolve", body=note.strip(), extra=extra, action="dispute.resolved", port_call=port_call)
    recompute_after_dispute_change(port_call=port_call, actor=actor)
    return dispute


@transaction.atomic
def reject(*, actor, dispute, note):
    _party_check(actor, dispute, agent=True)
    require(note and note.strip(), "A note is required.", {"note": ["Required."]})
    port_call = lock_port_call(dispute.port_call)
    dispute = lock(dispute)
    _change(dispute, actor, "reject", body=note.strip(), extra=_close_extra(actor, ResolutionType.REJECTED, note.strip()),
            action="dispute.rejected", port_call=port_call)
    recompute_after_dispute_change(port_call=port_call, actor=actor)
    return dispute


@transaction.atomic
def withdraw(*, actor, dispute):
    _party_check(actor, dispute, owner=True)
    port_call = lock_port_call(dispute.port_call)
    dispute = lock(dispute)
    _change(dispute, actor, "withdraw", extra=_close_extra(actor, ResolutionType.WITHDRAWN, ""), action="dispute.withdrawn", port_call=port_call)
    recompute_after_dispute_change(port_call=port_call, actor=actor)
    return dispute


@transaction.atomic
def reopen(*, actor, dispute, body=""):
    _party_check(actor, dispute, owner=True)
    port_call = lock_port_call(dispute.port_call)
    dispute = lock(dispute)
    if dispute.reopen_count >= 1:
        raise InvalidTransition("A dispute can be reopened only once.")
    if port_call.status not in (PortCallStatus.FDA_ISSUED, PortCallStatus.DISPUTED):
        raise InvalidTransition(f"Disputes cannot be reopened while the port call is {port_call.status}.")
    if Dispute.objects.filter(line_item=dispute.line_item, status__in=DISPUTE_LIVE).exclude(pk=dispute.pk).exists():
        raise InvalidTransition("Another dispute on this line is already open.")
    _change(dispute, actor, "reopen", body=body,
            extra={"reopen_count": dispute.reopen_count + 1, "resolution_type": None, "resolution_note": "", "resolved_by_user": None,
                   "resolved_at": None},
            action="dispute.reopened", port_call=port_call)
    recompute_after_dispute_change(port_call=port_call, actor=actor)
    return dispute


def live_dispute_status():
    return DisputeStatus.OPEN
