"""Vendor invoices (STATE_MACHINES.md §5)."""
from django.db import transaction
from django.utils import timezone

from apps.core.audit import audit, diff
from apps.core.enums import AccountStatus, InvoiceStatus, PaymentKind, RequestStatus, RequestType
from apps.core.exceptions import Forbidden, InvalidTransition, ValidationFailed
from apps.core.money import round_money, sum_money, to_decimal
from apps.core.services import lock, require, transition
from apps.masterdata.models import Currency, ServiceCategory
from apps.portcalls.models import PortCall
from apps.portcalls.services import ensure_mutable_for_vendor_work, lock_port_call
from apps.requests.models import Request

from .models import VendorInvoice, VendorInvoiceLine
from .transitions import INVOICE_MACHINE

EDITABLE_FIELDS = ["invoice_number", "issue_date", "due_date", "notes"]


def _require_vendor(actor, invoice):
    if actor.organization_id != invoice.vendor_organization_id:
        raise Forbidden("Only the issuing merchant can do that.")


def _require_billed_agent(actor, invoice):
    if actor.organization_id != invoice.agent_organization_id:
        raise Forbidden("Only the billed agent can do that.")


def _validate_amounts(data, currency):
    subtotal = round_money(to_decimal(data.get("subtotal_amount")), currency)
    tax = round_money(to_decimal(data.get("tax_amount") or "0"), currency)
    require(subtotal >= 0 and tax >= 0, "Amounts must not be negative.")
    total = round_money(to_decimal(data.get("total_amount", subtotal + tax)), currency)
    require(total == subtotal + tax, "Total must equal subtotal + tax.", {"total_amount": [f"Expected {subtotal + tax}."]})
    lines = data.get("lines") or []
    if lines:
        line_sum = sum_money([round_money(to_decimal(l.get("amount")), currency) for l in lines], currency)
        require(line_sum == subtotal, "Invoice lines must add up to the subtotal.", {"lines": [f"Lines sum to {line_sum}."]})
    return subtotal, tax, total


def _write_lines(invoice, lines):
    invoice.lines.all().delete()
    for line_no, line in enumerate(lines or [], start=1):
        quantity = to_decimal(line.get("quantity") or "1")
        require(quantity > 0, "Line quantity must be positive.")
        VendorInvoiceLine.objects.create(
            invoice=invoice,
            line_no=line_no,
            description=(line.get("description") or "")[:300] or f"Line {line_no}",
            quantity=quantity,
            unit=line.get("unit") or "",
            unit_amount=round_money(to_decimal(line.get("unit_amount") or line.get("amount")), invoice.currency_id),
            amount=round_money(to_decimal(line.get("amount")), invoice.currency_id),
        )


@transaction.atomic
def create_invoice(*, actor, data):
    port_call = PortCall.objects.filter(pk=data.get("port_call_id")).first()
    if port_call is None:
        raise ValidationFailed("Port call not found.", {"port_call_id": ["Invalid."]})
    port_call = lock_port_call(port_call)
    ensure_mutable_for_vendor_work(port_call)
    vendor_request = Request.objects.filter(
        pk=data.get("vendor_request_id"),
        request_type=RequestType.VENDOR_SERVICE,
        port_call=port_call,
        to_organization_id=actor.organization_id,
        status=RequestStatus.ACCEPTED,
    ).first()
    if vendor_request is None:
        raise Forbidden("You need an accepted service request on this port call to invoice it.")
    category = ServiceCategory.objects.filter(pk=data.get("service_category_id"), is_active=True).first()
    require(category is not None, "Unknown service category.", {"service_category_id": ["Invalid."]})
    currency = data.get("currency_code") or "INR"
    require(Currency.objects.filter(code=currency, is_active=True).exists(), "Unknown currency.", {"currency_code": ["Invalid."]})
    number = (data.get("invoice_number") or "").strip()
    require(number, "Invoice number is required.", {"invoice_number": ["Required."]})
    if VendorInvoice.objects.filter(vendor_organization_id=actor.organization_id, invoice_number=number).exists():
        raise ValidationFailed("You already used this invoice number.", {"invoice_number": ["Duplicate."]}, code="conflict")
    subtotal, tax, total = _validate_amounts(data, currency)
    invoice = VendorInvoice.objects.create(
        port_call=port_call,
        vendor_organization_id=actor.organization_id,
        agent_organization_id=port_call.agent_organization_id,
        vendor_request=vendor_request,
        service_category=category,
        invoice_number=number,
        issue_date=data.get("issue_date") or timezone.now().date(),
        due_date=data.get("due_date"),
        currency_id=currency,
        subtotal_amount=subtotal,
        tax_amount=tax,
        total_amount=total,
        file=data.get("file"),
        submitted_by_user=actor,
        notes=data.get("notes") or "",
    )
    _write_lines(invoice, data.get("lines"))
    audit(actor=actor, action="invoice.created", entity=invoice, port_call=port_call, to_state=invoice.status,
          metadata={"total": total, "currency": currency})
    return invoice


@transaction.atomic
def update_invoice(*, actor, invoice, data):
    invoice = lock(invoice)
    _require_vendor(actor, invoice)
    if invoice.status != InvoiceStatus.DRAFT:
        raise InvalidTransition("Only draft invoices can be edited.", {"status": invoice.status})
    currency = data.get("currency_code") or invoice.currency_id
    merged = {
        "subtotal_amount": data.get("subtotal_amount", invoice.subtotal_amount),
        "tax_amount": data.get("tax_amount", invoice.tax_amount),
        "lines": data.get("lines"),
    }
    if "total_amount" in data:
        merged["total_amount"] = data["total_amount"]
    subtotal, tax, total = _validate_amounts(merged, currency)
    values = {k: data[k] for k in EDITABLE_FIELDS if k in data}
    values.update(subtotal_amount=subtotal, tax_amount=tax, total_amount=total, currency_id=currency)
    if "service_category_id" in data:
        require(ServiceCategory.objects.filter(pk=data["service_category_id"], is_active=True).exists(), "Unknown service category.")
        values["service_category_id"] = data["service_category_id"]
    if "file" in data:
        values["file"] = data["file"]
    changes = diff(invoice, values)
    invoice.save()
    if data.get("lines") is not None:
        _write_lines(invoice, data["lines"])
    audit(actor=actor, action="invoice.updated", entity=invoice, port_call=invoice.port_call, changes=changes)
    return invoice


@transaction.atomic
def issue_invoice(*, actor, invoice):
    port_call = lock_port_call(invoice.port_call)
    invoice = lock(invoice)
    _require_vendor(actor, invoice)
    ensure_mutable_for_vendor_work(port_call)
    require(invoice.file_id is not None, "Attach the invoice document before issuing.", {"file_id": ["Required."]})
    return transition(machine=INVOICE_MACHINE, instance=invoice, event="issue", actor=actor, action="invoice.issued", port_call=port_call)


@transaction.atomic
def accept_invoice(*, actor, invoice, note=""):
    port_call = lock_port_call(invoice.port_call)
    invoice = lock(invoice)
    _require_billed_agent(actor, invoice)
    return transition(machine=INVOICE_MACHINE, instance=invoice, event="accept", actor=actor, action="invoice.accepted", port_call=port_call,
                      extra_updates={"reviewed_by_user": actor, "reviewed_at": timezone.now(), "review_note": note or ""})


@transaction.atomic
def reject_invoice(*, actor, invoice, note):
    require(note, "A note is required.", {"note": ["Required."]})
    port_call = lock_port_call(invoice.port_call)
    invoice = lock(invoice)
    _require_billed_agent(actor, invoice)
    return transition(machine=INVOICE_MACHINE, instance=invoice, event="reject", actor=actor, action="invoice.rejected", port_call=port_call,
                      metadata={"note": note}, extra_updates={"reviewed_by_user": actor, "reviewed_at": timezone.now(), "review_note": note})


@transaction.atomic
def reopen_invoice(*, actor, invoice):
    port_call = lock_port_call(invoice.port_call)
    invoice = lock(invoice)
    _require_vendor(actor, invoice)
    ensure_mutable_for_vendor_work(port_call)
    return transition(machine=INVOICE_MACHINE, instance=invoice, event="reopen", actor=actor, action="invoice.reopened", port_call=port_call)


@transaction.atomic
def void_invoice(*, actor, invoice):
    port_call = lock_port_call(invoice.port_call)
    invoice = lock(invoice)
    _require_vendor(actor, invoice)
    return transition(machine=INVOICE_MACHINE, instance=invoice, event="void", actor=actor, action="invoice.voided", port_call=port_call)


def mark_invoice_paid(*, actor, invoice, port_call):
    invoice = lock(invoice)
    return transition(machine=INVOICE_MACHINE, instance=invoice, event="mark_paid", actor=actor, action="invoice.paid", port_call=port_call,
                      extra_updates={"paid_at": timezone.now()})


@transaction.atomic
def pay_invoice(*, actor, invoice, data):
    """POST /vendor-invoices/{id}/mark-paid: records a CONFIRMED VENDOR_PAYMENT and sets PAID."""
    from apps.payments.services import record_payment

    lock_port_call(invoice.port_call)
    invoice = lock(invoice)
    _require_billed_agent(actor, invoice)
    if invoice.status != InvoiceStatus.ACCEPTED:
        raise InvalidTransition("Only accepted invoices can be paid.", {"status": invoice.status})
    payload = {**data, "kind": PaymentKind.VENDOR_PAYMENT}
    payload.setdefault("amount", invoice.total_amount)
    payload.setdefault("currency_code", invoice.currency_id)
    payment = record_payment(actor=actor, port_call=invoice.port_call, data=payload, vendor_invoice=invoice, auto_confirm=True)
    invoice.refresh_from_db()
    return invoice, payment


def fda_line_for(invoice):
    line = invoice.fda_lines.select_related("account").exclude(account__status=AccountStatus.VOID).order_by("-account__version").first()
    return line
