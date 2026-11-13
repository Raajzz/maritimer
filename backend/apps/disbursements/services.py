"""PDA / FDA services (STATE_MACHINES.md §4, ARCHITECTURE.md §3.4)."""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import AgentProfile, Organization
from apps.core.audit import audit
from apps.core.enums import AccountKind, AccountStatus, InvoiceStatus, OrgType, PortCallStatus
from apps.core.exceptions import Conflict, InvalidTransition, ValidationFailed
from apps.core.money import convert, round_money, sum_money, to_decimal
from apps.core.services import require, transition
from apps.masterdata.models import Currency, ServiceCategory
from apps.masterdata.services import resolve_rate
from apps.portcalls.services import has_live_disputes, lock_port_call, require_agent, require_owner, set_status

from .models import DisbursementAccount, DisbursementLineItem
from .transitions import FDA_MACHINE, PDA_MACHINE

INVOICE_USABLE = [InvoiceStatus.ACCEPTED, InvoiceStatus.PAID]


def machine_for(account):
    return PDA_MACHINE if account.kind == AccountKind.PDA else FDA_MACHINE


def current_account(port_call, kind):
    return DisbursementAccount.objects.filter(port_call=port_call, kind=kind, is_current=True).first()


def reference_pda(port_call):
    """The PDA FDA variance is measured against: the approved one, else the latest issued version."""
    approved = DisbursementAccount.objects.filter(port_call=port_call, kind=AccountKind.PDA, status=AccountStatus.APPROVED).order_by("-version").first()
    if approved:
        return approved
    return (
        DisbursementAccount.objects.filter(port_call=port_call, kind=AccountKind.PDA)
        .exclude(status__in=[AccountStatus.DRAFT, AccountStatus.VOID])
        .order_by("-version")
        .first()
    )


def _lock_account(account):
    return DisbursementAccount.objects.select_for_update().get(pk=account.pk)


def _rate_as_of(account, port_call):
    if account.kind == AccountKind.FDA and port_call.atd:
        return port_call.atd
    return timezone.now()


def _recompute_total(account):
    total = sum_money(account.line_items.values_list("amount", flat=True), account.currency_id)
    account.total_amount = total
    account.save(update_fields=["total_amount", "updated_at"])
    return total


def _reference(port_call, kind, version):
    return f"{kind}-{port_call.reference}-v{version}"


# ---- Line computation -------------------------------------------------------


def compute_line(*, account, port_call, data, existing=None, index=0):
    """Validate one line payload and return model field values. The server computes `amount`."""
    errors_key = f"line_items[{index}]"
    is_fda = account.kind == AccountKind.FDA
    values = {}

    invoice = None
    invoice_id = data.get("vendor_invoice_id", existing.vendor_invoice_id if existing else None)
    if invoice_id:
        require(is_fda, "Only FDA lines can reference vendor invoices.", {errors_key: ["vendor_invoice_id not allowed on a PDA."]})
        from apps.invoices.models import VendorInvoice

        invoice = VendorInvoice.objects.filter(pk=invoice_id, port_call=port_call).first()
        require(invoice is not None, "Vendor invoice not found on this port call.", {errors_key: ["Invalid vendor_invoice_id."]})
        require(invoice.status in INVOICE_USABLE, "Only accepted invoices can be added to an FDA.", {errors_key: [f"Invoice is {invoice.status}."]})

    category_id = data.get("service_category_id") or (invoice.service_category_id if invoice else None) or (existing.service_category_id if existing else None)
    category = ServiceCategory.objects.filter(pk=category_id).first()
    require(category is not None, "Unknown service category.", {errors_key: ["Invalid service_category_id."]})

    if invoice is not None:
        local_currency = invoice.currency_id
        local_amount = invoice.total_amount
        if "local_amount" in data and data["local_amount"] is not None and to_decimal(data["local_amount"]) != invoice.total_amount:
            raise ValidationFailed("Invoice-backed lines carry the invoice total.", {errors_key: ["local_amount must equal the invoice total."]})
        if data.get("local_currency_code") and data["local_currency_code"] != invoice.currency_id:
            raise ValidationFailed("Invoice-backed lines use the invoice currency.", {errors_key: ["local_currency_code mismatch."]})
    else:
        local_currency = data.get("local_currency_code") or (existing.local_currency_id if existing else account.currency_id)
        raw_amount = data.get("local_amount", existing.local_amount if existing else None)
        require(raw_amount is not None, "Amount is required.", {errors_key: ["local_amount required."]})
        local_amount = round_money(to_decimal(raw_amount), local_currency)
    require(Currency.objects.filter(code=local_currency, is_active=True).exists(), "Unknown currency.", {errors_key: ["Invalid local_currency_code."]})
    is_adjustment = bool(existing and existing.is_adjustment)
    require(is_adjustment or local_amount >= 0, "Amounts must not be negative.", {errors_key: ["local_amount must be ≥ 0."]})

    quantity = to_decimal(data.get("quantity", existing.quantity if existing else "1"))
    require(quantity > 0, "Quantity must be positive.", {errors_key: ["quantity must be > 0."]})

    if "fx_rate_id" in data:
        rate_id = data.get("fx_rate_id")
    elif existing is not None and existing.local_currency_id == local_currency:
        rate_id = existing.fx_rate_id
    else:
        rate_id = None
    applied = resolve_rate(local_currency, account.currency_id, rate_id=rate_id, as_of=_rate_as_of(account, port_call))
    amount = convert(local_amount, applied.applied, account.currency_id)
    if data.get("amount") not in (None, ""):
        if to_decimal(data["amount"]) != amount:
            raise ValidationFailed(
                "Amount does not match local amount × FX rate.",
                {errors_key: [f"Expected amount {amount} {account.currency_id}."]},
            )

    pda_line_id = data.get("pda_line_item_id", existing.pda_line_item_id if existing else None)
    if pda_line_id:
        require(is_fda, "Only FDA lines link to PDA lines.", {errors_key: ["pda_line_item_id not allowed on a PDA."]})
        ok = DisbursementLineItem.objects.filter(pk=pda_line_id, account__port_call=port_call, account__kind=AccountKind.PDA).exists()
        require(ok, "PDA line not found on this port call.", {errors_key: ["Invalid pda_line_item_id."]})

    vendor_id = data.get("vendor_organization_id", existing.vendor_organization_id if existing else None)
    if invoice is not None:
        vendor_id = invoice.vendor_organization_id
    if vendor_id:
        require(
            Organization.objects.filter(pk=vendor_id, type=OrgType.MERCHANT).exists(),
            "Vendor must be a merchant organization.",
            {errors_key: ["Invalid vendor_organization_id."]},
        )

    description = (data.get("description") or (existing.description if existing else "") or category.name).strip()
    values.update(
        service_category=category,
        description=description[:300],
        vendor_organization_id=vendor_id,
        quantity=quantity,
        unit=(data.get("unit", existing.unit if existing else "lot") or "lot")[:16],
        local_amount=local_amount,
        local_currency_id=local_currency,
        fx_rate=applied.fx_rate,
        fx_rate_applied=applied.applied,
        amount=amount,
        pda_line_item_id=pda_line_id,
        vendor_invoice=invoice,
        notes=data.get("notes", existing.notes if existing else "") or "",
    )
    return values


@transaction.atomic
def replace_lines(*, actor, account, lines, port_call=None):
    port_call = port_call or lock_port_call(account.port_call)
    account = _lock_account(account)
    require_agent(actor, port_call)
    if account.status != AccountStatus.DRAFT:
        raise InvalidTransition("Only draft accounts can be edited.", {"status": account.status})
    require(isinstance(lines, list), "line_items must be a list.")
    existing = {line.pk: line for line in account.line_items.all()}
    keep_ids = {item.get("id") for item in lines if item.get("id")}
    unknown = keep_ids - set(existing)
    require(not unknown, "Unknown line ids.", {"line_items": [f"Lines {sorted(unknown)} are not on this account."]})

    from apps.disputes.models import Dispute

    for line_id, line in existing.items():
        if line_id in keep_ids:
            continue
        if Dispute.objects.filter(adjustment_line_item=line).exists() or line.is_adjustment:
            raise ValidationFailed("Dispute adjustment lines cannot be removed.", {"line_items": [f"Line {line.line_no} is a dispute adjustment."]})
        line.delete()

    computed = []
    for index, item in enumerate(lines):
        line = existing.get(item.get("id"))
        computed.append((line, compute_line(account=account, port_call=port_call, data=item, existing=line, index=index)))

    seen_invoices = set()
    for _, values in computed:
        invoice = values.get("vendor_invoice")
        if invoice is not None:
            require(invoice.pk not in seen_invoices, "An invoice can back only one line.", {"line_items": [f"Invoice {invoice.invoice_number} repeated."]})
            seen_invoices.add(invoice.pk)

    # Two-phase renumbering avoids transient (account, line_no) collisions.
    for offset, line in enumerate(l for l, _ in computed if l is not None):
        DisbursementLineItem.objects.filter(pk=line.pk).update(line_no=-(offset + 1))
    for line_no, (line, values) in enumerate(computed, start=1):
        if line is None:
            DisbursementLineItem.objects.create(account=account, line_no=line_no, **values)
        else:
            for key, value in values.items():
                setattr(line, key, value)
            line.line_no = line_no
            line.save()
    total = _recompute_total(account)
    audit(actor=actor, action=f"{account.kind.lower()}.lines_replaced", entity=account, port_call=port_call,
          metadata={"line_count": len(computed), "total": total, "currency": account.currency_id})
    return account


# ---- PDA ----------------------------------------------------------------------


def _default_fee_line(port_call):
    profile = AgentProfile.objects.filter(organization_id=port_call.agent_organization_id).first()
    fee_category = ServiceCategory.objects.filter(is_agent_fee=True).first()
    if not profile or profile.default_agency_fee_amount is None or fee_category is None:
        return None
    return {
        "service_category_id": fee_category.pk,
        "description": fee_category.name,
        "local_amount": profile.default_agency_fee_amount,
        "local_currency_code": profile.default_agency_fee_currency_id,
    }


def _copy_lines(source, target, *, keep_links):
    for line in source.line_items.all().order_by("line_no"):
        DisbursementLineItem.objects.create(
            account=target,
            line_no=line.line_no,
            service_category_id=line.service_category_id,
            description=line.description,
            vendor_organization_id=line.vendor_organization_id,
            quantity=line.quantity,
            unit=line.unit,
            local_amount=line.local_amount,
            local_currency_id=line.local_currency_id,
            fx_rate_id=line.fx_rate_id,
            fx_rate_applied=line.fx_rate_applied,
            amount=line.amount,
            pda_line_item_id=line.pda_line_item_id if keep_links else None,
            vendor_invoice_id=line.vendor_invoice_id if keep_links else None,
            supersedes_line_item=line,
            is_adjustment=line.is_adjustment,
            source_dispute_id=line.source_dispute_id,
            notes=line.notes,
        )
    target.total_amount = source.total_amount
    target.save(update_fields=["total_amount", "updated_at"])


def _new_version(*, actor, port_call, previous, kind, notes=""):
    # Max+1, not previous+1: a discarded (VOID) revision keeps its version number.
    last = DisbursementAccount.objects.filter(port_call=port_call, kind=kind).order_by("-version").values_list("version", flat=True).first()
    version = (last or 0) + 1
    if previous is not None:
        previous.is_current = False
        previous.save(update_fields=["is_current", "updated_at"])
    return DisbursementAccount.objects.create(
        port_call=port_call,
        kind=kind,
        version=version,
        is_current=True,
        reference=_reference(port_call, kind, version),
        currency_id=port_call.settlement_currency_id,
        supersedes=previous,
        prepared_by_user=actor,
        notes=notes or (previous.notes if previous else ""),
    )


@transaction.atomic
def create_pda(*, actor, port_call, notes="", line_items=None):
    port_call = lock_port_call(port_call)
    require_agent(actor, port_call)
    if port_call.status != PortCallStatus.PDA_PENDING:
        raise InvalidTransition(f"A PDA can be prepared only while the port call is PDA_PENDING (now {port_call.status}).")
    current = current_account(port_call, AccountKind.PDA)
    if current is not None:
        if current.status == AccountStatus.REJECTED:
            return revise(actor=actor, account=current, notes=notes, line_items=line_items)
        raise Conflict(f"A current PDA already exists ({current.reference}, {current.status}).")
    account = _new_version(actor=actor, port_call=port_call, previous=None, kind=AccountKind.PDA, notes=notes)
    audit(actor=actor, action="pda.created", entity=account, port_call=port_call, to_state=account.status)
    if line_items is None:
        fee = _default_fee_line(port_call)
        line_items = [fee] if fee else []
    if line_items:
        replace_lines(actor=actor, account=account, lines=line_items, port_call=port_call)
    account.refresh_from_db()
    return account


@transaction.atomic
def issue(*, actor, account):
    port_call = lock_port_call(account.port_call)
    account = _lock_account(account)
    require_agent(actor, port_call)
    require(account.is_current, "Only the current version can be issued.")
    require(account.line_items.exists(), "Add at least one line before issuing.")
    if account.kind == AccountKind.FDA:
        bad = account.line_items.filter(vendor_invoice__isnull=False).exclude(vendor_invoice__status__in=INVOICE_USABLE)
        require(not bad.exists(), "Every invoice-backed line must reference an accepted invoice.")
    transition(machine=machine_for(account), instance=account, event="issue", actor=actor, action=f"{account.kind.lower()}.issued",
               port_call=port_call, metadata={"total": account.total_amount}, extra_updates={"issued_at": timezone.now()})
    if account.kind == AccountKind.PDA:
        set_status(port_call=port_call, event="pda_issue", actor=actor, action="port_call.pda_sent")
    elif port_call.status == PortCallStatus.DEPARTED:
        set_status(port_call=port_call, event="fda_issue", actor=actor, action="port_call.fda_issued")
    else:
        PORT_CALL_FDA_PHASE = {PortCallStatus.FDA_ISSUED, PortCallStatus.DISPUTED}
        if port_call.status not in PORT_CALL_FDA_PHASE:
            raise InvalidTransition(f"An FDA cannot be issued while the port call is {port_call.status}.")
    return account


@transaction.atomic
def approve_pda(*, actor, account, note=""):
    port_call = lock_port_call(account.port_call)
    account = _lock_account(account)
    require_owner(actor, port_call)
    require(account.kind == AccountKind.PDA and account.is_current, "Only the current PDA can be approved.")
    transition(machine=PDA_MACHINE, instance=account, event="approve", actor=actor, action="pda.approved", port_call=port_call,
               extra_updates={"owner_responded_by_user": actor, "owner_responded_at": timezone.now(), "owner_response_note": note or ""})
    set_status(port_call=port_call, event="pda_approve", actor=actor, action="port_call.pda_approved")
    return account


@transaction.atomic
def reject_pda(*, actor, account, note):
    require(note, "A reason is required.", {"note": ["Required."]})
    port_call = lock_port_call(account.port_call)
    account = _lock_account(account)
    require_owner(actor, port_call)
    require(account.kind == AccountKind.PDA and account.is_current, "Only the current PDA can be rejected.")
    transition(machine=PDA_MACHINE, instance=account, event="reject", actor=actor, action="pda.rejected", port_call=port_call,
               metadata={"note": note},
               extra_updates={"owner_responded_by_user": actor, "owner_responded_at": timezone.now(), "owner_response_note": note})
    set_status(port_call=port_call, event="pda_reject", actor=actor, action="port_call.pda_rejected", metadata={"note": note})
    return account


@transaction.atomic
def accept_fda(*, actor, account, note=""):
    port_call = lock_port_call(account.port_call)
    account = _lock_account(account)
    require_owner(actor, port_call)
    require(account.kind == AccountKind.FDA and account.is_current, "Only the current FDA can be accepted.")
    if account.status != AccountStatus.ISSUED:
        raise InvalidTransition("Only an issued FDA can be accepted.", {"status": account.status})
    account.owner_responded_by_user = actor
    account.owner_responded_at = timezone.now()
    account.owner_response_note = note or ""
    account.save()
    audit(actor=actor, action="fda.accepted", entity=account, port_call=port_call, metadata={"note": note})
    return account


@transaction.atomic
def revise(*, actor, account, notes=None, line_items=None, port_call=None):
    port_call = port_call or lock_port_call(account.port_call)
    account = _lock_account(account)
    require_agent(actor, port_call)
    require(account.is_current, "Only the current version can be revised.")
    machine = machine_for(account)
    if account.kind == AccountKind.FDA:
        require(port_call.status in (PortCallStatus.FDA_ISSUED, PortCallStatus.DISPUTED), f"FDA cannot be revised while port call is {port_call.status}.")
    transition(machine=machine, instance=account, event="revise", actor=actor, action=f"{account.kind.lower()}.superseded", port_call=port_call)
    new = _new_version(actor=actor, port_call=port_call, previous=account, kind=account.kind, notes=notes or account.notes)
    _copy_lines(account, new, keep_links=account.kind == AccountKind.FDA)
    audit(actor=actor, action=f"{account.kind.lower()}.revised", entity=new, port_call=port_call, to_state=new.status,
          metadata={"supersedes": account.reference, "version": new.version})
    if account.kind == AccountKind.PDA:
        set_status(port_call=port_call, event="pda_revise", actor=actor, action="port_call.pda_revising")
    if line_items is not None:
        replace_lines(actor=actor, account=new, lines=line_items, port_call=port_call)
    new.refresh_from_db()
    return new


@transaction.atomic
def discard(*, actor, account):
    from apps.disputes.models import Dispute

    port_call = lock_port_call(account.port_call)
    account = _lock_account(account)
    require_agent(actor, port_call)
    require(account.kind == AccountKind.FDA, "Only FDA revision drafts can be discarded.")
    require(account.version > 1 and account.supersedes_id, "Only a revision (version > 1) can be discarded.")
    if Dispute.objects.filter(resolved_in_account=account).exists():
        raise InvalidTransition("This draft carries dispute adjustments and cannot be discarded.")
    transition(machine=FDA_MACHINE, instance=account, event="discard", actor=actor, action="fda.discarded", port_call=port_call,
               extra_updates={"is_current": False})
    previous = _lock_account(account.supersedes)
    transition(machine=FDA_MACHINE, instance=previous, event="restore", actor=actor, action="fda.restored", port_call=port_call,
               extra_updates={"is_current": True})
    return previous


# ---- FDA builder ---------------------------------------------------------------


@transaction.atomic
def generate_fda(*, actor, port_call, fx_rate_ids=None, notes=""):
    from apps.invoices.models import VendorInvoice

    port_call = lock_port_call(port_call)
    require_agent(actor, port_call)
    fx_rate_ids = {k.upper(): v for k, v in (fx_rate_ids or {}).items()}
    current = current_account(port_call, AccountKind.FDA)
    if current is None:
        if port_call.status != PortCallStatus.DEPARTED:
            raise InvalidTransition(f"The FDA can be generated after departure (port call is {port_call.status}).")
        account = _new_version(actor=actor, port_call=port_call, previous=None, kind=AccountKind.FDA, notes=notes)
        audit(actor=actor, action="fda.created", entity=account, port_call=port_call, to_state=account.status)
    elif current.status == AccountStatus.DRAFT and current.version == 1:
        account = _lock_account(current)
        account.line_items.all().delete()
        if notes:
            account.notes = notes
            account.save(update_fields=["notes", "updated_at"])
    else:
        raise InvalidTransition("An FDA already exists; revise it instead of regenerating.", {"current": current.reference, "status": current.status})

    as_of = port_call.atd or timezone.now()
    pda = reference_pda(port_call)
    pda_lines = list(pda.line_items.all().order_by("line_no")) if pda else []
    unmatched_pda = list(pda_lines)

    def match_pda(category_id):
        for line in unmatched_pda:
            if line.service_category_id == category_id:
                unmatched_pda.remove(line)
                return line.pk
        return None

    lines, missing_pairs, warnings = [], set(), []
    invoices = VendorInvoice.objects.filter(port_call=port_call, status__in=INVOICE_USABLE).select_related("vendor_organization", "service_category").order_by("issue_date", "id")
    for invoice in invoices:
        payload = {
            "vendor_invoice_id": invoice.pk,
            "service_category_id": invoice.service_category_id,
            "description": f"{invoice.service_category.name} — {invoice.vendor_organization.display_name} inv. {invoice.invoice_number}",
            "pda_line_item_id": match_pda(invoice.service_category_id),
        }
        if invoice.currency_id != port_call.settlement_currency_id:
            payload["fx_rate_id"] = fx_rate_ids.get(invoice.currency_id)
            if not payload["fx_rate_id"]:
                try:
                    payload["fx_rate_id"] = resolve_rate(invoice.currency_id, port_call.settlement_currency_id, as_of=as_of).fx_rate.pk
                except ValidationFailed:
                    missing_pairs.add(f"{invoice.currency_id}/{port_call.settlement_currency_id}")
                    continue
        lines.append(payload)

    fee_category = ServiceCategory.objects.filter(is_agent_fee=True).first()
    fee_source = next((l for l in pda_lines if fee_category and l.service_category_id == fee_category.pk), None)
    fee = None
    if fee_source is not None:
        fee = {"service_category_id": fee_source.service_category_id, "description": fee_source.description,
               "local_amount": fee_source.local_amount, "local_currency_code": fee_source.local_currency_id}
    else:
        fee = _default_fee_line(port_call)
        if fee is None:
            warnings.append("No agency fee found on the PDA or agent profile; add it manually.")
    if fee is not None:
        fee["pda_line_item_id"] = match_pda(fee["service_category_id"])
        if fee["local_currency_code"] != port_call.settlement_currency_id:
            override = fx_rate_ids.get(fee["local_currency_code"])
            if override:
                fee["fx_rate_id"] = override
            else:
                try:
                    fee["fx_rate_id"] = resolve_rate(fee["local_currency_code"], port_call.settlement_currency_id, as_of=as_of).fx_rate.pk
                except ValidationFailed:
                    missing_pairs.add(f"{fee['local_currency_code']}/{port_call.settlement_currency_id}")
                    fee = None
        if fee is not None:
            lines.append(fee)

    if missing_pairs:
        raise ValidationFailed(
            "FX rates are missing for some invoice currencies. Record them and try again.",
            {"missing_pairs": sorted(missing_pairs)},
            code="fx_rate_missing",
        )
    for line in unmatched_pda:
        warnings.append(f"PDA line '{line.description}' has no invoice; add it as an agent-paid line if it was incurred.")
    if not lines:
        warnings.append("No accepted vendor invoices yet.")

    rule = "explicit rate ids " + ", ".join(f"{k}=#{v}" for k, v in fx_rate_ids.items()) + "; otherwise " if fx_rate_ids else ""
    account.fx_policy_note = f"{rule}latest rate with as_of ≤ ATD ({as_of:%Y-%m-%d %H:%M} UTC) per currency pair."
    account.save(update_fields=["fx_policy_note", "updated_at"])
    replace_lines(actor=actor, account=account, lines=lines, port_call=port_call)
    audit(actor=actor, action="fda.generated", entity=account, port_call=port_call,
          metadata={"invoice_count": len([l for l in lines if l.get("vendor_invoice_id")]), "fx_rule": account.fx_policy_note, "warnings": warnings})
    account.refresh_from_db()
    return account, warnings


@transaction.atomic
def finalize_fda(*, actor, account):
    from apps.payments.services import create_settlement

    port_call = lock_port_call(account.port_call)
    account = _lock_account(account)
    require_agent(actor, port_call)
    require(account.kind == AccountKind.FDA and account.is_current, "Only the current FDA can be finalized.")
    if has_live_disputes(port_call):
        raise InvalidTransition("Resolve all open disputes before finalizing the FDA.", code="open_disputes")
    if port_call.status != PortCallStatus.FDA_ISSUED:
        raise InvalidTransition(f"FDA can be finalized only when the port call is FDA_ISSUED (now {port_call.status}).")
    window = int(getattr(settings, "FDA_DISPUTE_WINDOW_DAYS", 0))
    if window > 0 and account.owner_responded_at is None and account.issued_at and timezone.now() < account.issued_at + timedelta(days=window):
        raise InvalidTransition(f"The owner has {window} day(s) to review the FDA before it can be finalized.")
    transition(machine=FDA_MACHINE, instance=account, event="finalize", actor=actor, action="fda.finalized", port_call=port_call,
               metadata={"total": account.total_amount}, extra_updates={"finalized_at": timezone.now()})
    set_status(port_call=port_call, event="fda_finalize", actor=actor, action="port_call.fda_final")
    settlement = create_settlement(actor=actor, port_call=port_call, fda=account)
    return account, settlement


# ---- Read-side computation --------------------------------------------------------


def variance(fda):
    """Per-PDA-line and total variance (not stored; SCHEMA.md §2.6)."""
    pda = reference_pda(fda.port_call)
    currency = fda.currency_id
    pda_lines = list(pda.line_items.select_related("service_category").order_by("line_no")) if pda else []
    fda_lines = list(fda.line_items.select_related("service_category").order_by("line_no"))
    rows = []
    linked = {}
    for line in fda_lines:
        if line.pda_line_item_id:
            linked.setdefault(line.pda_line_item_id, []).append(line)
    pda_ids = {l.pk for l in pda_lines}
    for pda_line in pda_lines:
        matched = linked.get(pda_line.pk, [])
        fda_amount = sum_money([l.amount for l in matched], currency)
        rows.append({
            "service_category_id": pda_line.service_category_id,
            "category": pda_line.service_category.name,
            "description": pda_line.description,
            "pda_line_item_id": pda_line.pk,
            "fda_line_item_ids": [l.pk for l in matched],
            "pda_amount": pda_line.amount,
            "fda_amount": fda_amount,
            "variance": round_money(fda_amount - pda_line.amount, currency),
        })
    for line in fda_lines:
        if line.pda_line_item_id in pda_ids:
            continue
        rows.append({
            "service_category_id": line.service_category_id,
            "category": line.service_category.name,
            "description": line.description,
            "pda_line_item_id": None,
            "fda_line_item_ids": [line.pk],
            "pda_amount": Decimal("0.00"),
            "fda_amount": line.amount,
            "variance": line.amount,
        })
    pda_total = pda.total_amount if pda else Decimal("0.00")
    return {
        "currency_code": currency,
        "pda_id": pda.pk if pda else None,
        "pda_reference": pda.reference if pda else None,
        "lines": rows,
        "pda_total": pda_total,
        "fda_total": fda.total_amount,
        "total_variance": round_money(fda.total_amount - pda_total, currency),
    }
