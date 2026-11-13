"""End-to-end lifecycle through the HTTP API: request → PDA → advance → vendors → FDA → dispute → settlement → rating."""
from decimal import Decimal

import pytest

from conftest import pdf_upload, svc


def ok(response, status=200):
    assert response.status_code == status, response.content
    return response.json()


@pytest.mark.django_db
def test_full_port_call_lifecycle_over_api(world):
    owner, agent, merchant = world.client(world.owner), world.client(world.agent), world.client(world.merchant)
    from datetime import timedelta

    def ago(days, hours=0):
        return (world.now - timedelta(days=days, hours=hours)).isoformat()

    # Discovery: agents serving Mumbai, sorted by rating
    agents = ok(owner.get(f"/api/v1/agents?port_id={world.port.pk}&sort=-rating"))
    assert {a["legal_name"] for a in agents["results"]} >= {"Agent Co", "Other Agent Co"}

    # Owner → agent request
    req = ok(owner.post("/api/v1/requests", {
        "request_type": "PORT_CALL", "to_organization_id": world.agent_org.pk, "subject": "MV Test – Mumbai", "message": "Crew change x2",
        "details": {"vessel_id": world.vessel.pk, "port_id": world.port.pk, "eta": ago(10), "etd": ago(7),
                    "cargo_type_id": world.cargo.pk, "cargo_quantity": "24000", "cargo_unit": "MT"},
        "services": [{"service_category_id": svc("PILOTAGE").pk}, {"service_category_id": svc("TOWAGE").pk}],
    }, format="json"), 201)
    assert req["status"] == "PENDING"
    assert ok(agent.get("/api/v1/requests?direction=incoming"))["count"] == 1
    accepted = ok(agent.post(f"/api/v1/requests/{req['id']}/accept", {"note": "On it"}, format="json"))
    pc_id = accepted["port_call"]["id"]
    assert accepted["chat_thread_id"]

    # PDA
    pda = ok(agent.post(f"/api/v1/port-calls/{pc_id}/pda", {"line_items": world.pda_lines()}, format="json"), 201)
    assert pda["total"] == {"amount": "4600.00", "currency_code": "USD"}
    detail = ok(agent.get(f"/api/v1/port-calls/{pc_id}"))
    assert "pda.issue" in detail["allowed_actions"]
    ok(agent.post(f"/api/v1/disbursement-accounts/{pda['id']}/issue"))
    assert "pda.approve" in ok(owner.get(f"/api/v1/port-calls/{pc_id}"))["allowed_actions"]
    ok(owner.post(f"/api/v1/disbursement-accounts/{pda['id']}/approve", {"note": "ok"}, format="json"))

    # Advance: owner records, agent confirms
    pay = ok(owner.post(f"/api/v1/port-calls/{pc_id}/payments", {"kind": "ADVANCE", "amount": "4000.00", "currency_code": "USD",
                                                                  "paid_at": ago(12), "bank_reference": "TT-1"}, format="json"), 201)
    assert pay["status"] == "PENDING"
    assert owner.post(f"/api/v1/payments/{pay['id']}/confirm").status_code == 403
    ok(agent.post(f"/api/v1/payments/{pay['id']}/confirm"))
    assert ok(agent.get(f"/api/v1/port-calls/{pc_id}"))["status"] == "ADVANCE_RECEIVED"

    ok(agent.post(f"/api/v1/port-calls/{pc_id}/arrive", {"ata": ago(10)}, format="json"))

    # Vendor sourcing + negotiation chat
    vr = ok(agent.post("/api/v1/requests", {"request_type": "VENDOR_SERVICE", "to_organization_id": world.merchant_org.pk, "port_call_id": pc_id,
                                            "subject": "Pilotage", "services": [{"service_category_id": svc("PILOTAGE").pk}]}, format="json"), 201)
    vr = ok(merchant.post(f"/api/v1/requests/{vr['id']}/accept", {}, format="json"))
    thread = vr["chat_thread_id"]
    ok(agent.post(f"/api/v1/chat/threads/{thread}/messages", {"body": "Rate?"}, format="json"), 201)
    msg = ok(merchant.post(f"/api/v1/chat/threads/{thread}/messages", {"body": "INR 95,000"}, format="json"), 201)
    threads = ok(agent.get("/api/v1/chat/threads"))["results"]
    assert next(t for t in threads if t["id"] == thread)["unread_count"] == 1
    ok(agent.post(f"/api/v1/chat/threads/{thread}/read", {"last_read_message_id": msg["id"]}, format="json"))
    polled = ok(agent.get(f"/api/v1/chat/threads/{thread}/messages?after_id={msg['id'] - 1}"))
    assert [m["body"] for m in polled["results"]] == ["INR 95,000"]
    assert owner.get(f"/api/v1/chat/threads/{thread}").status_code == 404  # owners never see agent↔merchant threads

    # Merchant invoice (INR) with uploaded file
    f = ok(merchant.post("/api/v1/files", {"file": pdf_upload(), "purpose": "INVOICE"}, format="multipart"), 201)
    inv = ok(merchant.post("/api/v1/vendor-invoices", {
        "port_call_id": pc_id, "vendor_request_id": vr["id"], "service_category_id": svc("PILOTAGE").pk, "invoice_number": "P-001",
        "issue_date": ago(7)[:10], "currency_code": "INR", "subtotal_amount": "95000.00", "tax_amount": "0.00", "total_amount": "95000.00",
        "file_id": f["id"]}, format="json"), 201)
    assert agent.get(f"/api/v1/vendor-invoices/{inv['id']}").status_code == 404  # drafts are private to the merchant
    ok(merchant.post(f"/api/v1/vendor-invoices/{inv['id']}/issue"))
    ok(agent.post(f"/api/v1/vendor-invoices/{inv['id']}/accept", {}, format="json"))

    # Departure and FDA
    assert agent.post(f"/api/v1/port-calls/{pc_id}/fda/generate", {}, format="json").status_code == 409  # not departed yet
    ok(agent.post(f"/api/v1/port-calls/{pc_id}/depart", {"atd": ago(7)}, format="json"))
    fda = ok(agent.post(f"/api/v1/port-calls/{pc_id}/fda/generate", {}, format="json"), 201)
    assert any("Port dues" in w for w in fda["warnings"])
    lines = [{"id": l["id"]} for l in fda["line_items"]]
    pda_detail = ok(agent.get(f"/api/v1/disbursement-accounts/{pda['id']}"))
    dues_pda_line = next(l for l in pda_detail["line_items"] if l["service_category"]["code"] == "PORT_DUES")
    lines.append({"service_category_id": svc("PORT_DUES").pk, "description": "Port dues", "local_amount": "200000.00",
                  "local_currency_code": "INR", "pda_line_item_id": dues_pda_line["id"]})
    fda = ok(agent.put(f"/api/v1/disbursement-accounts/{fda['id']}/line-items", {"line_items": lines}, format="json"))
    # 95,000 × 0.012 = 1140 ; fee 1000 ; dues 200,000 × 0.012 = 2400  → 4540
    assert fda["total"]["amount"] == "4540.00"
    assert fda["variance"]["total_variance"] == "-60.00"
    ok(agent.post(f"/api/v1/disbursement-accounts/{fda['id']}/issue"))

    # Dispute → finalize blocked → resolve with adjustment → re-issue → finalize
    pilot_line = next(l for l in fda["line_items"] if l["vendor_invoice_id"] == inv["id"])
    dispute = ok(owner.post("/api/v1/disputes", {"line_item_id": pilot_line["id"], "reason": "Quoted 90k in chat"}, format="json"), 201)
    assert ok(owner.get(f"/api/v1/port-calls/{pc_id}"))["status"] == "DISPUTED"
    blocked = agent.post(f"/api/v1/disbursement-accounts/{fda['id']}/finalize")
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "open_disputes"
    ok(agent.post(f"/api/v1/disputes/{dispute['id']}/comment", {"body": "Checking"}, format="json"), 201)
    resolved = ok(agent.post(f"/api/v1/disputes/{dispute['id']}/resolve", {"resolution_type": "ADJUSTED", "note": "Agreed 90k",
                                                                             "adjusted_local_amount": "90000.00"}, format="json"))
    assert resolved["status"] == "RESOLVED" and len(resolved["events"]) >= 3
    fda_v2 = ok(agent.get(f"/api/v1/port-calls/{pc_id}/fda"))
    assert fda_v2["version"] == 2 and fda_v2["total"]["amount"] == "4480.00"
    ok(agent.post(f"/api/v1/disbursement-accounts/{fda_v2['id']}/issue"))
    ok(agent.post(f"/api/v1/disbursement-accounts/{fda_v2['id']}/finalize"))

    # Settlement: 4480 − 4000 → owner owes 480
    settlement = ok(owner.get(f"/api/v1/port-calls/{pc_id}/settlement"))
    assert settlement["direction"] == "BALANCE_DUE" and settlement["outstanding"]["amount"] == "480.00"
    bal = ok(owner.post(f"/api/v1/port-calls/{pc_id}/payments", {"kind": "BALANCE", "amount": "480.00", "paid_at": ago(1)}, format="json"), 201)
    ok(agent.post(f"/api/v1/payments/{bal['id']}/confirm"))
    assert ok(agent.get(f"/api/v1/port-calls/{pc_id}"))["status"] == "SETTLED"

    # Vendor gets paid, call closes, owner rates
    paid = ok(agent.post(f"/api/v1/vendor-invoices/{inv['id']}/mark-paid", {"bank_reference": "NEFT-1"}, format="json"))
    assert paid["status"] == "PAID" and paid["payment"]["amount"]["currency_code"] == "INR"
    ok(agent.post(f"/api/v1/port-calls/{pc_id}/close"))
    ok(owner.post(f"/api/v1/port-calls/{pc_id}/ratings", {"ratee_organization_id": world.agent_org.pk, "score": 4, "comment": "Good"}, format="json"), 201)
    assert owner.post(f"/api/v1/port-calls/{pc_id}/ratings", {"ratee_organization_id": world.agent_org.pk, "score": 5}, format="json").status_code == 409
    profile = ok(owner.get(f"/api/v1/agents/{world.agent_org.pk}"))["profile"]
    assert profile["rating_avg"] == "4.00" and profile["rating_count"] == 1 and profile["completed_port_calls"] == 1

    # Timeline + dashboards render
    timeline = ok(agent.get(f"/api/v1/port-calls/{pc_id}/timeline?page_size=100"))
    assert timeline["count"] > 20
    assert ok(agent.get("/api/v1/dashboard"))["role"] == "AGENT"
    assert ok(owner.get("/api/v1/dashboard"))["role"] == "OWNER"
    assert ok(merchant.get("/api/v1/dashboard"))["role"] == "MERCHANT"
    assert Decimal(ok(world.client(world.admin).get("/api/v1/admin/dashboard"))["users_by_role"]["OWNER"]) >= 2


@pytest.mark.django_db
def test_error_envelope_shape(world):
    r = world.client(world.owner).post("/api/v1/requests", {"request_type": "NOPE"}, format="json")
    body = r.json()
    assert r.status_code == 400 and set(body["error"]) == {"code", "message", "details"} and body["error"]["code"] == "validation_error"


@pytest.mark.django_db
def test_money_is_serialized_as_strings(world):
    out = world.stage("PDA_SENT")
    body = world.client(world.owner).get(f"/api/v1/disbursement-accounts/{out['pda'].pk}").json()
    line = body["line_items"][0]
    assert isinstance(line["local_amount"], str) and isinstance(line["amount"], str) and isinstance(line["fx_rate_applied"], str)


@pytest.mark.django_db
def test_upload_rejects_disguised_files(world):
    from django.core.files.uploadedfile import SimpleUploadedFile

    fake = SimpleUploadedFile("x.pdf", b"MZ\x90\x00 not a pdf", content_type="application/pdf")
    r = world.client(world.merchant).post("/api/v1/files", {"file": fake, "purpose": "INVOICE"}, format="multipart")
    assert r.status_code == 400


@pytest.mark.django_db
def test_file_download_token_and_access(world):
    f = world.client(world.merchant).post("/api/v1/files", {"file": pdf_upload(), "purpose": "CHAT"}, format="multipart").json()
    assert world.client(world.owner2).get(f"/api/v1/files/{f['id']}").status_code == 404
    url = f["download_url"].replace("http://testserver", "")
    r = world.client().get(url)
    assert r.status_code == 200 and b"".join(r.streaming_content).startswith(b"%PDF")
    assert world.client().get(url + "tampered").status_code == 404
