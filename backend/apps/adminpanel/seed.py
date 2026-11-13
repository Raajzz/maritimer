"""Seed data. `seed_masterdata` is safe in production; `seed_demo` builds demo orgs, users and port calls
by calling the real service functions, so the demo exercises the same rules as the API."""
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.enums import AccountKind, FilePurpose, RequestType, ResolutionType, Role
from apps.masterdata.models import CargoType, Country, Currency, FxRate, Location, Port, ServiceCategory
from apps.requests.models import RequestRolePolicy

COUNTRIES = [
    ("IN", "IND", "India"), ("SG", "SGP", "Singapore"), ("AE", "ARE", "United Arab Emirates"), ("LK", "LKA", "Sri Lanka"),
    ("MY", "MYS", "Malaysia"), ("CN", "CHN", "China"), ("NL", "NLD", "Netherlands"), ("GR", "GRC", "Greece"),
    ("PA", "PAN", "Panama"), ("LR", "LBR", "Liberia"), ("MH", "MHL", "Marshall Islands"), ("GB", "GBR", "United Kingdom"),
    ("US", "USA", "United States"), ("JP", "JPN", "Japan"), ("KR", "KOR", "South Korea"),
]
CURRENCIES = [("USD", "US Dollar", "$", 2), ("INR", "Indian Rupee", "₹", 2), ("SGD", "Singapore Dollar", "S$", 2),
              ("AED", "UAE Dirham", "AED", 2), ("EUR", "Euro", "€", 2), ("MYR", "Malaysian Ringgit", "RM", 2)]
LOCATIONS = [
    ("IN", "Mumbai", "Maharashtra", [("Mumbai Port", "INBOM", "Asia/Kolkata", "18.9500", "72.8400"),
                                     ("Jawaharlal Nehru Port (Nhava Sheva)", "INNSA", "Asia/Kolkata", "18.9490", "72.9510")]),
    ("IN", "Chennai", "Tamil Nadu", [("Chennai Port", "INMAA", "Asia/Kolkata", "13.0960", "80.2920")]),
    ("IN", "Kandla", "Gujarat", [("Deendayal Port (Kandla)", "INIXY", "Asia/Kolkata", "23.0330", "70.2200")]),
    ("IN", "Kochi", "Kerala", [("Cochin Port", "INCOK", "Asia/Kolkata", "9.9670", "76.2670")]),
    ("SG", "Singapore", "", [("Port of Singapore", "SGSIN", "Asia/Singapore", "1.2640", "103.8400")]),
    ("AE", "Dubai", "", [("Jebel Ali", "AEJEA", "Asia/Dubai", "25.0110", "55.0610")]),
    ("LK", "Colombo", "Western", [("Port of Colombo", "LKCMB", "Asia/Colombo", "6.9500", "79.8450")]),
    ("MY", "Port Klang", "Selangor", [("Port Klang", "MYPKG", "Asia/Kuala_Lumpur", "3.0000", "101.3920")]),
]
SERVICES = [
    ("PORT_DUES", "Port dues", False, False), ("PILOTAGE", "Pilotage", True, False), ("TOWAGE", "Towage (tugs)", True, False),
    ("BERTH_HIRE", "Berth hire", False, False), ("MOORING", "Mooring / unmooring", True, False),
    ("CUSTOMS_CLEARANCE", "Customs clearance", True, False), ("IMMIGRATION", "Crew immigration", True, False),
    ("FRESH_WATER", "Fresh water", True, False), ("PROVISIONS", "Provisions & stores", True, False), ("BUNKERS", "Bunkers", True, False),
    ("CREW_CHANGE", "Crew change", True, False), ("CASH_TO_MASTER", "Cash to master", False, False),
    ("LAUNCH_SERVICE", "Launch / boat service", True, False), ("GARBAGE_DISPOSAL", "Garbage disposal", True, False),
    ("SURVEY", "Survey & inspection", True, False), ("STEVEDORING", "Stevedoring", True, False),
    ("AGENCY_FEE", "Agency fee", False, True), ("OTHER", "Other", True, False),
]
CARGO = [("CONTAINER", "Containers"), ("DRY_BULK", "Dry bulk"), ("LIQUID_BULK", "Liquid bulk"), ("BREAK_BULK", "Break bulk"),
         ("RORO", "Ro-Ro"), ("LNG_LPG", "LNG / LPG"), ("PROJECT", "Project cargo"), ("PASSENGER", "Passengers"),
         ("BALLAST", "In ballast"), ("OTHER", "Other")]
POLICIES = [
    (RequestType.PORT_CALL, "OWNER", "AGENT", True, False),
    (RequestType.VENDOR_SERVICE, "AGENT", "MERCHANT", True, True),
    # Present but disabled: flipping is_enabled opens the direction without a schema change (SCHEMA.md D5).
    (RequestType.VENDOR_SERVICE, "MERCHANT", "AGENT", False, True),
    (RequestType.PORT_CALL, "AGENT", "OWNER", False, False),
]


@transaction.atomic
def seed_masterdata(stdout=None):
    for code, iso3, name in COUNTRIES:
        Country.objects.update_or_create(code=code, defaults={"iso3": iso3, "name": name})
    for code, name, symbol, units in CURRENCIES:
        Currency.objects.update_or_create(code=code, defaults={"name": name, "symbol": symbol, "minor_units": units})
    for country, name, region, ports in LOCATIONS:
        location = Location.objects.filter(country_id=country, name__iexact=name).first() or Location.objects.create(
            country_id=country, name=name, region=region)
        for port_name, unlocode, tz, lat, lng in ports:
            Port.objects.update_or_create(unlocode=unlocode, defaults={
                "location": location, "name": port_name, "timezone": tz, "latitude": Decimal(lat), "longitude": Decimal(lng)})
    for order, (code, name, vendor, fee) in enumerate(SERVICES):
        ServiceCategory.objects.update_or_create(code=code, defaults={
            "name": name, "is_vendor_service": vendor, "is_agent_fee": fee, "sort_order": order * 10})
    for code, name in CARGO:
        CargoType.objects.update_or_create(code=code, defaults={"name": name})
    for request_type, from_role, to_role, enabled, needs_call in POLICIES:
        RequestRolePolicy.objects.get_or_create(
            request_type=request_type, from_role=from_role, to_role=to_role,
            defaults={"is_enabled": enabled, "requires_port_call": needs_call, "creates_chat_thread": True},
        )
    if stdout:
        stdout.write(f"Master data: {Country.objects.count()} countries, {Port.objects.count()} ports, "
                     f"{ServiceCategory.objects.count()} service categories, {RequestRolePolicy.objects.count()} request policies.")


# ---- Demo ---------------------------------------------------------------------------

DEMO_MARKER = "Bombay Port Agencies Pvt Ltd"


def _svc(code):
    return ServiceCategory.objects.get(code=code)


def _port(code):
    return Port.objects.get(unlocode=code)


def _demo_pdf(title, lines):
    """Small invoice PDF for demo attachments (WeasyPrint if available, else a minimal hand-built PDF)."""
    try:
        from apps.documents.pdf import html_to_pdf

        rows = "".join(f"<tr><td>{d}</td><td style='text-align:right'>{a}</td></tr>" for d, a in lines)
        return html_to_pdf(f"<html><body style='font-family:sans-serif'><h2>{title}</h2><table width='100%'>{rows}</table></body></html>")
    except Exception:
        text = f"{title} " + " ".join(f"{d} {a}" for d, a in lines)
        text = text.replace("(", "").replace(")", "")[:200]
        stream = f"BT /F1 12 Tf 40 780 Td ({text}) Tj ET".encode()
        objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
                b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
                b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
        out, offsets = b"%PDF-1.4\n", []
        for i, obj in enumerate(objs, start=1):
            offsets.append(len(out))
            out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
        out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
        out += f"trailer << /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
        return out


def seed_demo(*, admin_email, owner_email, agent_email, merchant_emails, stdout=None):
    from apps.accounts import services as acc
    from apps.accounts.models import Organization, User
    from apps.chat.models import ChatThread
    from apps.chat.services import post_message
    from apps.disbursements import services as da
    from apps.disputes import services as disp
    from apps.documents.services import store_bytes
    from apps.invoices import services as inv
    from apps.masterdata.services import record_fx_rate
    from apps.payments import services as pay
    from apps.portcalls import services as pcs
    from apps.ratings.services import rate
    from apps.requests import services as req
    from apps.vessels.models import Vessel

    def log(msg):
        if stdout:
            stdout.write(msg)

    seed_masterdata(stdout)
    if Organization.objects.filter(legal_name=DEMO_MARKER).exists():
        log("Demo data already present; nothing to do. (Run `manage.py flush` first to rebuild it.)")
        return

    now = timezone.now()
    admin, _ = acc.bootstrap_admin(email=admin_email, display_name="Demo Admin")

    # FX rates (INR→USD direct quotes, plus one USD→INR quote to show inverse handling)
    for days, rate_value in ((45, "0.0119500000"), (20, "0.0120100000"), (8, "0.0119800000"), (1, "0.0120000000")):
        record_fx_rate(actor=admin, base_currency_code="INR", quote_currency_code="USD", rate=rate_value,
                       as_of=now - timedelta(days=days), source_reference="Demo rate (RBI reference)")
    record_fx_rate(actor=admin, base_currency_code="SGD", quote_currency_code="USD", rate="0.7450000000", as_of=now - timedelta(days=20))
    record_fx_rate(actor=admin, base_currency_code="USD", quote_currency_code="AED", rate="3.6725000000", as_of=now - timedelta(days=20))

    mumbai = Location.objects.get(name="Mumbai")
    singapore = Location.objects.get(name="Singapore")
    agent_services = [_svc(c).pk for c in ("PILOTAGE", "TOWAGE", "CUSTOMS_CLEARANCE", "IMMIGRATION", "CREW_CHANGE", "FRESH_WATER", "PROVISIONS")]

    def org(type_, name, country, city, locations, ports, services=None, profile=None, **extra):
        return acc.admin_create_organization(
            actor=admin, type=type_,
            organization={"legal_name": name, "country_code": country, "city": city, "email": f"ops@{name.split()[0].lower()}.example",
                          "phone": "+91 22 5555 0100" if country == "IN" else "+65 6555 0100", "address_line1": extra.get("address", "1 Harbour Road")},
            profile=profile or {}, coverage={"location_ids": locations, "port_ids": ports, "service_category_ids": services or []},
        )

    owner = org("OWNER", "Lion City Shipping Pte Ltd", "SG", "Singapore", [singapore.pk, mumbai.pk], [_port("SGSIN").pk, _port("INBOM").pk],
                profile={"operator_kind": "OWNER", "fleet_size": 6, "preferred_currency_code": "USD"})
    agent = org("AGENT", DEMO_MARKER, "IN", "Mumbai", [mumbai.pk], [_port("INBOM").pk, _port("INNSA").pk], agent_services,
                profile={"description": "Full-service port agency in Mumbai and Nhava Sheva since 1998.", "emergency_phone": "+91 98200 00000",
                         "default_agency_fee": {"amount": Decimal("1500.00"), "currency_code": "USD"}})
    agent2 = org("AGENT", "Konkan Marine Services LLP", "IN", "Mumbai", [mumbai.pk], [_port("INBOM").pk], agent_services[:4],
                 profile={"description": "Boutique agency focused on bulk carriers.", "default_agency_fee": {"amount": Decimal("1200.00"), "currency_code": "USD"}})
    org("AGENT", "Coromandel Shipping Agency", "IN", "Chennai", [Location.objects.get(name="Chennai").pk], [_port("INMAA").pk], agent_services[:3])
    pilots = org("MERCHANT", "Harbour Pilots & Tugs Pvt Ltd", "IN", "Mumbai", [mumbai.pk], [_port("INBOM").pk, _port("INNSA").pk],
                 [_svc("PILOTAGE").pk, _svc("TOWAGE").pk, _svc("MOORING").pk], profile={"default_currency_code": "INR"})
    supplies = org("MERCHANT", "Mumbai Marine Supplies", "IN", "Mumbai", [mumbai.pk], [_port("INBOM").pk],
                   [_svc("FRESH_WATER").pk, _svc("PROVISIONS").pk], profile={"default_currency_code": "INR", "catalog_notes": "Fresh water barges, dry & frozen provisions"})
    customs = org("MERCHANT", "Seaport Customs Brokers", "IN", "Mumbai", [mumbai.pk], [_port("INBOM").pk],
                  [_svc("CUSTOMS_CLEARANCE").pk, _svc("IMMIGRATION").pk], profile={"default_currency_code": "INR"})

    owner_user = acc.admin_create_org_user(actor=admin, organization=owner, email=owner_email, display_name="Wei Lin (Owner ops)")
    agent_user = acc.admin_create_org_user(actor=admin, organization=agent, email=agent_email, display_name="Priya Desai (Agent)")
    acc.admin_create_org_user(actor=admin, organization=agent2, email=f"konkan.{agent_email}", display_name="Konkan desk")
    m_users = [acc.admin_create_org_user(actor=admin, organization=o, email=e, display_name=n) for o, e, n in (
        (pilots, merchant_emails[0], "Harbour Pilots desk"), (supplies, merchant_emails[1], "Supplies desk"), (customs, merchant_emails[2], "Customs desk"))]
    pilots_user, supplies_user, customs_user = m_users

    vessels = [Vessel.objects.create(owner_organization=owner, name=n, imo_number=imo, vessel_type=t, flag_country_id=f, dwt=Decimal(d), grt=Decimal(g))
               for n, imo, t, f, d, g in (
                   ("MV Straits Pioneer", "9700001", "BULK_CARRIER", "SG", "58000", "32500"),
                   ("MV Lion Voyager", "9700002", "CONTAINER", "SG", "41000", "39900"),
                   ("MV Merlion Trader", "9700003", "GENERAL_CARGO", "PA", "18000", "12100"),
                   ("MT Temasek Spirit", "9700004", "TANKER", "MH", "74000", "42000"),
                   ("MV Orchard Star", "9700005", "BULK_CARRIER", "LR", "63000", "35800"),
                   ("MV Sentosa Bay", "9700006", "CONTAINER", "SG", "52000", "48000"))]
    bulk = CargoType.objects.get(code="DRY_BULK")
    containers = CargoType.objects.get(code="CONTAINER")

    def new_call(vessel, eta, etd, cargo, note, services=("PILOTAGE", "TOWAGE", "FRESH_WATER")):
        request = req.create_request(actor=owner_user, data={
            "request_type": RequestType.PORT_CALL, "to_organization_id": agent.pk, "subject": f"{vessel.name} – Mumbai",
            "message": note, "details": {"vessel_id": vessel.pk, "port_id": _port("INBOM").pk, "eta": eta, "etd": etd, "cargo_type_id": cargo.pk,
                                         "cargo_description": "Steel coils" if cargo == bulk else "Mixed containers", "cargo_quantity": "24000", "cargo_unit": "MT"},
            "services": [{"service_category_id": _svc(s).pk} for s in services]})
        _, port_call, _ = req.accept_request(actor=agent_user, request=request, note="Happy to assist.")
        return port_call

    def pda_lines(water_mt=300):
        return [
            {"service_category_id": _svc("PORT_DUES").pk, "description": "Port dues (GRT based)", "local_amount": "450000.00", "local_currency_code": "INR"},
            {"service_category_id": _svc("PILOTAGE").pk, "description": "Pilotage inward & outward", "local_amount": "185000.00", "local_currency_code": "INR"},
            {"service_category_id": _svc("TOWAGE").pk, "description": "Towage – 2 tugs in/out", "local_amount": "240000.00", "local_currency_code": "INR"},
            {"service_category_id": _svc("BERTH_HIRE").pk, "description": "Berth hire (3 days)", "local_amount": "95000.00", "local_currency_code": "INR"},
            {"service_category_id": _svc("CUSTOMS_CLEARANCE").pk, "description": "Customs & immigration clearance", "local_amount": "30000.00", "local_currency_code": "INR"},
            {"service_category_id": _svc("FRESH_WATER").pk, "description": f"Fresh water {water_mt} MT", "local_amount": "60000.00", "local_currency_code": "INR"},
            {"service_category_id": _svc("AGENCY_FEE").pk, "description": "Agency fee", "local_amount": "1500.00", "local_currency_code": "USD"},
        ]

    def through_pda(pc, advance=None):
        pda = da.create_pda(actor=agent_user, port_call=pc, notes="Estimate based on 3 days alongside.", line_items=pda_lines())
        da.issue(actor=agent_user, account=pda)
        da.approve_pda(actor=owner_user, account=pda, note="Approved.")
        if advance:
            p = pay.record_payment(actor=owner_user, port_call=pc, data={"kind": "ADVANCE", "amount": advance, "currency_code": "USD",
                                                                         "paid_at": pc.eta - timedelta(days=2), "bank_reference": "DBS-TT-" + pc.reference[-6:]})
            pay.confirm_payment(actor=agent_user, payment=p)
        return pda

    def vendor_job(pc, merchant_org, merchant_user, service, subject, number, amount, tax, issue_date):
        r = req.create_request(actor=agent_user, data={"request_type": RequestType.VENDOR_SERVICE, "to_organization_id": merchant_org.pk,
                                                       "port_call_id": pc.pk, "subject": subject, "message": "Please confirm availability and rate.",
                                                       "services": [{"service_category_id": _svc(service).pk}]})
        _, _, thread = req.accept_request(actor=merchant_user, request=r, note="Confirmed.")
        post_message(user=agent_user, thread=thread, body=f"Vessel {pc.vessel.name} ETA {pc.eta:%d %b %H:%M}. Please confirm rate in INR.")
        post_message(user=merchant_user, thread=thread, body=f"Confirmed. Rate INR {amount} + GST.")
        pdf = _demo_pdf(f"{merchant_org.legal_name} – Invoice {number}", [(subject, f"INR {amount}"), ("GST", f"INR {tax}")])
        stored = store_bytes(data=pdf, filename=f"{number}.pdf", content_type="application/pdf", purpose=FilePurpose.INVOICE, user=merchant_user)
        invoice = inv.create_invoice(actor=merchant_user, data={
            "port_call_id": pc.pk, "vendor_request_id": r.pk, "service_category_id": _svc(service).pk, "invoice_number": number,
            "issue_date": issue_date, "currency_code": "INR", "subtotal_amount": Decimal(amount), "tax_amount": Decimal(tax),
            "total_amount": Decimal(amount) + Decimal(tax), "file": stored})
        inv.issue_invoice(actor=merchant_user, invoice=invoice)
        return invoice

    # 1) Full lifecycle: PDA → advance → in port → vendors → FDA → disputes → final → refund → closed → rated
    pc1 = new_call(vessels[0], now - timedelta(days=14), now - timedelta(days=11), bulk, "Discharging steel coils. Crew change of 2 at berth.")
    through_pda(pc1, advance="15000.00")
    pcs.arrive(actor=agent_user, port_call=pc1, ata=now - timedelta(days=14, hours=-2))
    invoices = [
        vendor_job(pc1, pilots, pilots_user, "PILOTAGE", "Pilotage in/out", "HPT/24-25/0912", "172000.00", "30960.00", (now - timedelta(days=11)).date()),
        vendor_job(pc1, pilots, pilots_user, "TOWAGE", "Towage 2 tugs", "HPT/24-25/0913", "228000.00", "0.00", (now - timedelta(days=11)).date()),
        vendor_job(pc1, supplies, supplies_user, "FRESH_WATER", "Fresh water 320 MT", "MMS-7781", "64000.00", "0.00", (now - timedelta(days=12)).date()),
        vendor_job(pc1, customs, customs_user, "CUSTOMS_CLEARANCE", "Customs & immigration", "SCB-2219", "28000.00", "5040.00", (now - timedelta(days=11)).date()),
    ]
    for invoice in invoices:
        inv.accept_invoice(actor=agent_user, invoice=invoice, note="Checked against service report.")
    pcs.depart(actor=agent_user, port_call=pc1, atd=now - timedelta(days=11, hours=-3))
    fda, _ = da.generate_fda(actor=agent_user, port_call=pc1, notes="Final account with vendor invoices attached.")
    lines = [{"id": l.pk} for l in fda.line_items.all()]
    pda1 = da.current_account(pc1, AccountKind.PDA)
    pda_by_cat = {l.service_category.code: l.pk for l in pda1.line_items.select_related("service_category")}
    lines += [
        {"service_category_id": _svc("PORT_DUES").pk, "description": "Port dues (paid by agent to MbPT)", "local_amount": "452400.00",
         "local_currency_code": "INR", "pda_line_item_id": pda_by_cat["PORT_DUES"]},
        {"service_category_id": _svc("BERTH_HIRE").pk, "description": "Berth hire (3.5 days)", "local_amount": "110800.00",
         "local_currency_code": "INR", "pda_line_item_id": pda_by_cat["BERTH_HIRE"]},
    ]
    da.replace_lines(actor=agent_user, account=fda, lines=lines)
    da.issue(actor=agent_user, account=fda)
    fda.refresh_from_db()
    pilot_line = fda.line_items.get(vendor_invoice=invoices[0])
    water_line = fda.line_items.get(vendor_invoice=invoices[2])
    d1 = disp.open_dispute(actor=owner_user, line_item_id=pilot_line.pk, reason="Pilotage GST should be 12% not 18%; please correct.",
                           disputed_amount=str((pilot_line.amount * Decimal("0.95")).quantize(Decimal("0.01"))))
    d2 = disp.open_dispute(actor=owner_user, line_item_id=water_line.pk, reason="We ordered 300 MT, not 320 MT.")
    disp.acknowledge(actor=agent_user, dispute=d1)
    disp.comment(actor=agent_user, dispute=d1, body="Checked with the pilots — GST was over-charged. Crediting the difference.")
    disp.resolve(actor=agent_user, dispute=d1, resolution_type=ResolutionType.ADJUSTED, note="GST corrected to 12% (credit line added).",
                 adjusted_local_amount="192640.00", mode="CREDIT_LINE")
    disp.comment(actor=agent_user, dispute=d2, body="Master signed the receipt for 320 MT (attached to the invoice).")
    disp.reject(actor=agent_user, dispute=d2, note="Delivery receipt signed by Master confirms 320 MT.")
    da.issue(actor=agent_user, account=da.current_account(pc1, AccountKind.FDA))
    final, settlement = da.finalize_fda(actor=agent_user, account=da.current_account(pc1, AccountKind.FDA))
    if settlement.direction == "REFUND_DUE":
        p = pay.record_payment(actor=agent_user, port_call=pc1, data={"kind": "REFUND", "amount": abs(settlement.balance), "currency_code": "USD",
                                                                      "paid_at": now - timedelta(days=3), "bank_reference": "HDFC-REF-1101"})
        pay.confirm_payment(actor=owner_user, payment=p)
    elif settlement.direction == "BALANCE_DUE":
        p = pay.record_payment(actor=owner_user, port_call=pc1, data={"kind": "BALANCE", "amount": settlement.balance, "currency_code": "USD",
                                                                      "paid_at": now - timedelta(days=3), "bank_reference": "DBS-TT-1101"})
        pay.confirm_payment(actor=agent_user, payment=p)
    for invoice in invoices:
        inv.pay_invoice(actor=agent_user, invoice=invoice, data={"paid_at": now - timedelta(days=9), "bank_reference": f"NEFT-{invoice.invoice_number}"})
    thread = ChatThread.objects.get(port_call=pc1, kind="PORT_CALL")
    post_message(user=owner_user, thread=thread, body="Thanks for handling the crew change smoothly.")
    post_message(user=agent_user, thread=thread, body="Pleasure. The settlement has been remitted today.")
    pcs.close(actor=agent_user, port_call=pc1)
    rate(actor=owner_user, port_call=pc1, ratee_organization_id=agent.pk, score=5, comment="Fast turnaround and transparent FDA.")
    log(f"  {pc1.reference}: full lifecycle → CLOSED (settlement {settlement.direction}, balance {settlement.balance} USD)")

    # 2) FDA issued with an open dispute (DISPUTED)
    pc2 = new_call(vessels[4], now - timedelta(days=9), now - timedelta(days=6), bulk, "Loading bulk cargo.")
    through_pda(pc2, advance="13000.00")
    pcs.arrive(actor=agent_user, port_call=pc2, ata=now - timedelta(days=9))
    inv2 = [vendor_job(pc2, pilots, pilots_user, "PILOTAGE", "Pilotage in/out", "HPT/24-25/0950", "181000.00", "21720.00", (now - timedelta(days=6)).date()),
            vendor_job(pc2, supplies, supplies_user, "FRESH_WATER", "Fresh water 250 MT", "MMS-7802", "50000.00", "0.00", (now - timedelta(days=7)).date())]
    for invoice in inv2:
        inv.accept_invoice(actor=agent_user, invoice=invoice)
    pcs.depart(actor=agent_user, port_call=pc2, atd=now - timedelta(days=6))
    fda2, _ = da.generate_fda(actor=agent_user, port_call=pc2)
    da.issue(actor=agent_user, account=fda2)
    disp.open_dispute(actor=owner_user, line_item_id=fda2.line_items.get(vendor_invoice=inv2[0]).pk, reason="Pilotage higher than the PDA estimate; please explain.")
    log(f"  {pc2.reference}: FDA issued, dispute open → DISPUTED")

    # 3) Departed with accepted invoices, ready for FDA generation
    pc3 = new_call(vessels[1], now - timedelta(days=5), now - timedelta(days=2), containers, "Container discharge/load.")
    through_pda(pc3, advance="14000.00")
    pcs.arrive(actor=agent_user, port_call=pc3, ata=now - timedelta(days=5))
    for job in (vendor_job(pc3, pilots, pilots_user, "TOWAGE", "Towage 2 tugs", "HPT/24-25/0977", "236000.00", "0.00", (now - timedelta(days=2)).date()),):
        inv.accept_invoice(actor=agent_user, invoice=job)
    vendor_job(pc3, customs, customs_user, "CUSTOMS_CLEARANCE", "Customs & immigration", "SCB-2240", "29500.00", "5310.00", (now - timedelta(days=2)).date())
    pcs.depart(actor=agent_user, port_call=pc3, atd=now - timedelta(days=2))
    log(f"  {pc3.reference}: DEPARTED, one invoice awaiting review → ready for FDA")

    # 4) In port, vendor request pending with a merchant
    pc4 = new_call(vessels[3], now - timedelta(days=1), now + timedelta(days=2), CargoType.objects.get(code="LIQUID_BULK"), "Tanker discharge; fresh water needed.")
    through_pda(pc4, advance="12500.00")
    pcs.arrive(actor=agent_user, port_call=pc4, ata=now - timedelta(hours=20))
    req.create_request(actor=agent_user, data={"request_type": RequestType.VENDOR_SERVICE, "to_organization_id": supplies.pk, "port_call_id": pc4.pk,
                                               "subject": "Fresh water 200 MT", "message": "Alongside berth 7 tomorrow 0600.",
                                               "services": [{"service_category_id": _svc("FRESH_WATER").pk, "quantity": "200", "unit": "MT"}]})
    log(f"  {pc4.reference}: IN_PORT, vendor request pending with Mumbai Marine Supplies")

    # 5) PDA approved, advance recorded but not yet confirmed
    pc5 = new_call(vessels[2], now + timedelta(days=4), now + timedelta(days=7), bulk, "Break bulk discharge.")
    through_pda(pc5)
    pay.record_payment(actor=owner_user, port_call=pc5, data={"kind": "ADVANCE", "amount": "11000.00", "currency_code": "USD", "paid_at": now,
                                                              "bank_reference": "DBS-TT-5501"})
    log(f"  {pc5.reference}: PDA_APPROVED, advance awaiting agent confirmation")

    # 6) PDA sent, waiting for owner approval
    pc6 = new_call(vessels[5], now + timedelta(days=8), now + timedelta(days=10), containers, "Container call.")
    pda6 = da.create_pda(actor=agent_user, port_call=pc6, line_items=pda_lines(200))
    da.issue(actor=agent_user, account=pda6)
    log(f"  {pc6.reference}: PDA_SENT, waiting for owner approval")

    # 7) A brand-new request awaiting the agent, and one sent to the second agent
    req.create_request(actor=owner_user, data={
        "request_type": RequestType.PORT_CALL, "to_organization_id": agent.pk, "subject": "MV Straits Pioneer – Mumbai (next voyage)",
        "message": "Same rotation as last time.", "details": {"vessel_id": vessels[0].pk, "port_id": _port("INBOM").pk, "eta": now + timedelta(days=21),
                                                               "etd": now + timedelta(days=24), "cargo_type_id": bulk.pk},
        "services": [{"service_category_id": _svc("PILOTAGE").pk}, {"service_category_id": _svc("CREW_CHANGE").pk}]})
    log("  Pending port-call request for the agent dashboard 'Requested' column")

    # 8) A self-onboarded merchant waiting for admin review
    applicant = User.objects.create(email=f"applicant.{merchant_emails[0]}", display_name="New Vendor Applicant", firebase_uid=None)
    acc.choose_role(user=applicant, role=Role.MERCHANT, legal_name="Gateway Launch Services", country_code="IN")
    acc.update_organization(user=applicant, data={"legal_name": "Gateway Launch Services", "city": "Mumbai", "tax_id": "27ABCDE1234F1Z5"})
    acc.update_coverage(user=applicant, port_ids=[_port("INBOM").pk], service_category_ids=[_svc("LAUNCH_SERVICE").pk])
    doc = store_bytes(data=_demo_pdf("Certificate of incorporation", [("Gateway Launch Services", "CIN U63090MH2019PTC000000")]),
                      filename="incorporation.pdf", content_type="application/pdf", purpose=FilePurpose.VERIFICATION, user=applicant)
    acc.add_verification_document(user=applicant, document_type="COMPANY_REGISTRATION", title="Certificate of incorporation", file=doc)
    acc.submit_onboarding(user=applicant)
    log("  Merchant applicant awaiting admin approval")

    log("Demo users (sign in with Google using these emails, or `Bearer dev:<email>` when AUTH_DEV_TOKENS=true):")
    for label, email in (("Admin", admin_email), ("Owner", owner_email), ("Agent", agent_email), ("Merchant (pilots/tugs)", merchant_emails[0]),
                         ("Merchant (supplies)", merchant_emails[1]), ("Merchant (customs)", merchant_emails[2])):
        log(f"  {label:24} {email}")
