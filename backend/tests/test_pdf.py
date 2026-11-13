"""PDF generation (ARCHITECTURE.md §3.5). Skipped when WeasyPrint's system libraries are missing."""
import io

import pytest

try:
    import weasyprint  # noqa: F401

    HAVE_WEASY = True
except Exception:  # OSError when pango/cairo are absent
    HAVE_WEASY = False

pytestmark = pytest.mark.skipif(not HAVE_WEASY, reason="WeasyPrint system libraries not available")


@pytest.mark.django_db
def test_issued_pda_is_cached_and_draft_is_preview(world):
    from apps.documents.models import GeneratedDocument
    from apps.documents.pdf import account_pdf

    out = world.stage("PDA_PENDING")
    doc, data = account_pdf(out["pda"])
    assert doc is None and data.startswith(b"%PDF")  # draft: preview only
    out = world.stage("PDA_SENT")
    out["pda"].refresh_from_db()
    doc1, _ = account_pdf(out["pda"])
    doc2, _ = account_pdf(out["pda"])
    assert doc1.pk == doc2.pk and GeneratedDocument.objects.filter(disbursement_account=out["pda"]).count() == 1


@pytest.mark.django_db
def test_fda_pdf_appends_invoice_pdfs_and_settlement_statement(world):
    from pypdf import PdfReader

    from apps.documents.pdf import render_account_pdf, settlement_pdf
    from apps.documents.services import read_bytes

    out = world.stage("FDA_FINAL", advance="1500.00")
    pdf = render_account_pdf(out["fda"])
    reader = PdfReader(io.BytesIO(pdf))
    text = "".join(page.extract_text() for page in reader.pages)
    assert "Final Disbursement Account" in text and "Variance" in text
    assert len(reader.pages) >= 2  # FDA pages + appended vendor invoice
    doc, preview = settlement_pdf(out["settlement"])
    assert doc is None and b"%PDF" in preview[:8]  # open settlement → preview


@pytest.mark.django_db
def test_pdf_endpoint_redirects_or_returns_json(world):
    out = world.stage("PDA_SENT")
    c = world.client(world.owner)
    r = c.get(f"/api/v1/disbursement-accounts/{out['pda'].pk}/pdf")
    assert r.status_code == 302
    body = c.get(f"/api/v1/disbursement-accounts/{out['pda'].pk}/pdf?redirect=false").json()
    assert body["cached"] and body["file"]["content_type"] == "application/pdf"
