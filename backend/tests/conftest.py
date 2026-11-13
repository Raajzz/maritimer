"""Shared fixtures. `world` builds approved orgs/users for every role; `stage()` drives a port call
through the real services to any pipeline stage."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import services as acc
from apps.adminpanel.seed import seed_masterdata
from apps.core.enums import AccountKind, FilePurpose, RequestType
from apps.core.money import clear_minor_units_cache
from apps.masterdata.models import CargoType, Location, Port, ServiceCategory
from apps.masterdata.services import record_fx_rate
from apps.vessels.models import Vessel

PDF_BYTES = b"%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >> endobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer << /Size 4 /Root 1 0 R >>\nstartxref\n178\n%%EOF"


def svc(code):
    return ServiceCategory.objects.get(code=code)


def pdf_upload(name="invoice.pdf"):
    return SimpleUploadedFile(name, PDF_BYTES, content_type="application/pdf")


class World:
    """Approved organizations and users for each role plus master data."""

    def __init__(self):
        seed_masterdata()
        clear_minor_units_cache()
        self.now = timezone.now()
        self.admin, _ = acc.bootstrap_admin(email="admin@test.io")
        mumbai = Location.objects.get(name="Mumbai")
        self.port = Port.objects.get(unlocode="INBOM")
        self.cargo = CargoType.objects.get(code="DRY_BULK")

        def org(type_, name, services=(), fee=None):
            profile = {"default_agency_fee": {"amount": Decimal(fee), "currency_code": "USD"}} if fee else {}
            return acc.admin_create_organization(
                actor=self.admin, type=type_, organization={"legal_name": name, "country_code": "IN", "city": "Mumbai"},
                profile=profile, coverage={"location_ids": [mumbai.pk], "port_ids": [self.port.pk], "service_category_ids": [svc(s).pk for s in services]},
            )

        self.owner_org = org("OWNER", "Owner Co")
        self.owner2_org = org("OWNER", "Other Owner Co")
        self.agent_org = org("AGENT", "Agent Co", ("PILOTAGE", "TOWAGE"), fee="1000.00")
        self.agent2_org = org("AGENT", "Other Agent Co", ("PILOTAGE",))
        self.merchant_org = org("MERCHANT", "Pilots Co", ("PILOTAGE", "TOWAGE"))
        self.merchant2_org = org("MERCHANT", "Water Co", ("FRESH_WATER",))
        self.owner = acc.admin_create_org_user(actor=self.admin, organization=self.owner_org, email="owner@test.io")
        self.owner2 = acc.admin_create_org_user(actor=self.admin, organization=self.owner2_org, email="owner2@test.io")
        self.agent = acc.admin_create_org_user(actor=self.admin, organization=self.agent_org, email="agent@test.io")
        self.agent2 = acc.admin_create_org_user(actor=self.admin, organization=self.agent2_org, email="agent2@test.io")
        self.merchant = acc.admin_create_org_user(actor=self.admin, organization=self.merchant_org, email="merchant@test.io")
        self.merchant2 = acc.admin_create_org_user(actor=self.admin, organization=self.merchant2_org, email="merchant2@test.io")
        self.vessel = Vessel.objects.create(owner_organization=self.owner_org, name="MV Test", imo_number="9000001", vessel_type="BULK_CARRIER")
        # INR→USD 0.0120 from 30 days ago; a newer rate 0.0125 dated in the future relative to most ATDs in tests
        self.rate_old = record_fx_rate(actor=self.admin, base_currency_code="INR", quote_currency_code="USD", rate="0.0120000000",
                                       as_of=self.now - timedelta(days=30))
        self.rate_new = record_fx_rate(actor=self.admin, base_currency_code="INR", quote_currency_code="USD", rate="0.0125000000",
                                       as_of=self.now + timedelta(days=30))

    def client(self, user=None):
        c = APIClient()
        if user is not None:
            c.credentials(HTTP_AUTHORIZATION=f"Bearer dev:{user.email}")
        return c

    # ---- service-level drivers ---------------------------------------------------

    def port_call(self, eta_days=-10):
        from apps.requests import services as req

        eta = self.now + timedelta(days=eta_days)
        request = req.create_request(actor=self.owner, data={
            "request_type": RequestType.PORT_CALL, "to_organization_id": self.agent_org.pk, "subject": "Call",
            "details": {"vessel_id": self.vessel.pk, "port_id": self.port.pk, "eta": eta, "etd": eta + timedelta(days=3), "cargo_type_id": self.cargo.pk},
            "services": [{"service_category_id": svc("PILOTAGE").pk}],
        })
        _, pc, _ = req.accept_request(actor=self.agent, request=request)
        return pc

    PDA_LINES = [
        {"service_category_id": None, "code": "PILOTAGE", "local_amount": "100000.00", "local_currency_code": "INR"},
        {"service_category_id": None, "code": "PORT_DUES", "local_amount": "200000.00", "local_currency_code": "INR"},
        {"service_category_id": None, "code": "AGENCY_FEE", "local_amount": "1000.00", "local_currency_code": "USD"},
    ]

    def pda_lines(self):
        return [{**{k: v for k, v in l.items() if k != "code"}, "service_category_id": svc(l["code"]).pk} for l in self.PDA_LINES]

    def stage(self, target, *, advance="5000.00", invoice_amount="90000.00"):
        """Drive a new port call to `target` (CREATED, PDA_PENDING, PDA_SENT, PDA_APPROVED, ADVANCE_RECEIVED, IN_PORT,
        DEPARTED, FDA_ISSUED, FDA_FINAL). Returns a dict of the created objects."""
        from apps.disbursements import services as da
        from apps.invoices import services as inv
        from apps.payments import services as pay
        from apps.portcalls import services as pcs
        from apps.requests import services as req
        from apps.documents.services import store_bytes

        out = {"pc": self.port_call()}
        pc = out["pc"]
        if target == "CREATED":
            return out
        pda = da.create_pda(actor=self.agent, port_call=pc, line_items=self.pda_lines())
        out["pda"] = pda
        if target == "PDA_PENDING":
            return out
        da.issue(actor=self.agent, account=pda)
        if target == "PDA_SENT":
            return out
        da.approve_pda(actor=self.owner, account=pda)
        if target == "PDA_APPROVED":
            return out
        if advance:
            p = pay.record_payment(actor=self.owner, port_call=pc, data={"kind": "ADVANCE", "amount": advance, "currency_code": "USD", "paid_at": self.now})
            pay.confirm_payment(actor=self.agent, payment=p)
            out["advance"] = p
        if target == "ADVANCE_RECEIVED":
            return out
        pcs.arrive(actor=self.agent, port_call=pc, ata=self.now - timedelta(days=5))
        r = req.create_request(actor=self.agent, data={"request_type": RequestType.VENDOR_SERVICE, "to_organization_id": self.merchant_org.pk,
                                                       "port_call_id": pc.pk, "services": [{"service_category_id": svc("PILOTAGE").pk}]})
        req.accept_request(actor=self.merchant, request=r)
        out["vendor_request"] = r
        stored = store_bytes(data=PDF_BYTES, filename="inv.pdf", content_type="application/pdf", purpose=FilePurpose.INVOICE, user=self.merchant)
        invoice = inv.create_invoice(actor=self.merchant, data={
            "port_call_id": pc.pk, "vendor_request_id": r.pk, "service_category_id": svc("PILOTAGE").pk,
            "invoice_number": f"INV-{pc.pk}", "issue_date": self.now.date(), "currency_code": "INR",
            "subtotal_amount": Decimal(invoice_amount), "tax_amount": Decimal("0"), "total_amount": Decimal(invoice_amount), "file": stored})
        inv.issue_invoice(actor=self.merchant, invoice=invoice)
        inv.accept_invoice(actor=self.agent, invoice=invoice)
        out["invoice"] = invoice
        if target == "IN_PORT":
            return out
        pcs.depart(actor=self.agent, port_call=pc, atd=self.now - timedelta(days=2))
        if target == "DEPARTED":
            return out
        fda, _ = da.generate_fda(actor=self.agent, port_call=pc)
        da.issue(actor=self.agent, account=fda)
        out["fda"] = fda
        if target == "FDA_ISSUED":
            return out
        out["fda"], out["settlement"] = da.finalize_fda(actor=self.agent, account=da.current_account(pc, AccountKind.FDA))
        return out


@pytest.fixture
def world(db):
    return World()
