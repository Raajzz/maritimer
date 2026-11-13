"""PDF generation with WeasyPrint (ARCHITECTURE.md §3.5).

Issued/final documents are rendered once and cached in generated_documents keyed by
(entity, status); drafts and open settlements render a watermarked preview that is not stored.
"""
import base64
import io
import logging

from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.core.enums import AccountStatus, AccountKind, FilePurpose, GeneratedDocumentType, InvoiceStatus, SettlementStatus

from .models import GeneratedDocument
from .services import read_bytes, store_bytes

logger = logging.getLogger(__name__)

CACHEABLE_ACCOUNT_STATES = {AccountStatus.ISSUED, AccountStatus.APPROVED, AccountStatus.REJECTED, AccountStatus.SUPERSEDED, AccountStatus.FINAL}


def html_to_pdf(html: str) -> bytes:
    from weasyprint import HTML  # imported lazily: needs pango system libraries

    return HTML(string=html).write_pdf()


def _org_block(org):
    return {
        "name": org.legal_name,
        "trade_name": org.trade_name,
        "address": ", ".join(p for p in [org.address_line1, org.address_line2, org.city, org.postal_code, org.country.name] if p),
        "email": org.email,
        "phone": org.phone,
        "tax_id": org.tax_id,
    }


def _port_call_context(port_call):
    return {
        "reference": port_call.reference,
        "vessel": port_call.vessel,
        "port": port_call.port,
        "eta": port_call.eta,
        "etd": port_call.etd,
        "ata": port_call.ata,
        "atd": port_call.atd,
        "cargo_type": port_call.cargo_type.name,
        "owner": _org_block(port_call.owner_organization),
        "agent": _org_block(port_call.agent_organization),
    }


def _account_context(account):
    from apps.disbursements.services import variance

    lines = list(account.line_items.select_related("service_category", "vendor_organization", "vendor_invoice", "fx_rate").order_by("line_no"))
    context = {
        "account": account,
        "lines": lines,
        "port_call": _port_call_context(account.port_call),
        "generated_at": timezone.now(),
        "is_draft": account.status == AccountStatus.DRAFT,
        "title": "Proforma Disbursement Account" if account.kind == AccountKind.PDA else "Final Disbursement Account",
    }
    if account.kind == AccountKind.FDA:
        context["variance"] = variance(account)
        context["disputes"] = list(account.port_call.disputes.select_related("line_item").order_by("created_at"))
        context["invoices"] = [l.vendor_invoice for l in lines if l.vendor_invoice_id]
    return context


def _image_appendix(invoices):
    images = []
    for invoice in invoices:
        if invoice.file_id and invoice.file.content_type.startswith("image/"):
            data = base64.b64encode(read_bytes(invoice.file)).decode()
            images.append({"invoice": invoice, "data_uri": f"data:{invoice.file.content_type};base64,{data}"})
    return images


def render_account_pdf(account) -> bytes:
    context = _account_context(account)
    if account.kind == AccountKind.FDA:
        context["invoice_images"] = _image_appendix(context["invoices"])
    pdf = html_to_pdf(render_to_string("pdf/account.html", context))
    if account.kind == AccountKind.FDA:
        pdf = _append_invoice_pdfs(pdf, context["invoices"])
    return pdf


def _append_invoice_pdfs(pdf: bytes, invoices) -> bytes:
    attachments = [inv for inv in invoices if inv.file_id and inv.file.content_type == "application/pdf"]
    if not attachments:
        return pdf
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(pdf)))
    for invoice in attachments:
        try:
            writer.append(PdfReader(io.BytesIO(read_bytes(invoice.file))))
        except Exception:  # a corrupt vendor PDF must not block the FDA
            logger.warning("Could not append invoice %s PDF", invoice.pk, exc_info=True)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def render_settlement_pdf(settlement) -> bytes:
    from apps.payments.services import outstanding, paid_against

    context = {
        "settlement": settlement,
        "port_call": _port_call_context(settlement.port_call),
        "payments": list(settlement.port_call.payments.exclude(kind="VENDOR_PAYMENT").order_by("paid_at")),
        "paid": paid_against(settlement),
        "outstanding": outstanding(settlement),
        "abs_balance": abs(settlement.balance),
        "generated_at": timezone.now(),
        "is_draft": settlement.status != SettlementStatus.CLOSED,
    }
    return html_to_pdf(render_to_string("pdf/settlement.html", context))


def _filename(prefix, reference, status):
    return f"{prefix}-{reference}-{status.lower()}.pdf"


def account_pdf(account, user=None):
    """Return (GeneratedDocument | None, bytes | None). Cached docs return the row; previews return bytes."""
    status = account.status
    if status not in CACHEABLE_ACCOUNT_STATES:
        return None, render_account_pdf(account)
    existing = GeneratedDocument.objects.filter(disbursement_account=account, entity_status=status).select_related("file").first()
    if existing:
        return existing, None
    pdf = render_account_pdf(account)
    stored = store_bytes(data=pdf, filename=f"{account.reference}-{status.lower()}.pdf", content_type="application/pdf",
                         purpose=FilePurpose.GENERATED_PDF, user=None)
    try:
        with transaction.atomic():
            doc = GeneratedDocument.objects.create(
                port_call=account.port_call, document_type=account.kind, disbursement_account=account, entity_status=status,
                file=stored, generated_by_user=user,
            )
    except IntegrityError:  # concurrent render won the race
        doc = GeneratedDocument.objects.get(disbursement_account=account, entity_status=status)
    return doc, None


def settlement_pdf(settlement, user=None):
    if settlement.status != SettlementStatus.CLOSED:
        return None, render_settlement_pdf(settlement)
    existing = GeneratedDocument.objects.filter(settlement=settlement, entity_status=settlement.status).select_related("file").first()
    if existing:
        return existing, None
    pdf = render_settlement_pdf(settlement)
    stored = store_bytes(data=pdf, filename=f"{settlement.reference}.pdf", content_type="application/pdf",
                         purpose=FilePurpose.GENERATED_PDF, user=None)
    try:
        with transaction.atomic():
            doc = GeneratedDocument.objects.create(
                port_call=settlement.port_call, document_type=GeneratedDocumentType.SETTLEMENT_STATEMENT, settlement=settlement,
                entity_status=settlement.status, file=stored, generated_by_user=user,
            )
    except IntegrityError:
        doc = GeneratedDocument.objects.get(settlement=settlement, entity_status=settlement.status)
    return doc, None


__all__ = ["account_pdf", "settlement_pdf", "render_account_pdf", "render_settlement_pdf", "InvoiceStatus"]
