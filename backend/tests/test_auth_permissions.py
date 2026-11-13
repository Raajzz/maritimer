"""Authentication, approval gating, role gates and object scoping (API.md §0, §17)."""
from unittest import mock

import pytest

from apps.accounts.models import User
from apps.core.enums import UserStatus


@pytest.mark.django_db
def test_unauthenticated_is_401(world):
    r = world.client().get("/api/v1/port-calls")
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthenticated"


@pytest.mark.django_db
def test_health_is_public(world):
    assert world.client().get("/api/v1/health").json() == {"status": "ok"}


@pytest.mark.django_db
def test_dev_tokens_rejected_when_disabled(world, settings):
    settings.AUTH_DEV_TOKENS = False
    r = world.client(world.owner).get("/api/v1/auth/me")
    assert r.status_code == 401


@pytest.mark.django_db
def test_firebase_token_creates_new_user(world):
    claims = {"uid": "fb-123", "email": "New.Person@Example.com", "email_verified": True, "name": "New Person"}
    with mock.patch("apps.core.authentication.verify_firebase_token", return_value=claims):
        c = world.client()
        c.credentials(HTTP_AUTHORIZATION="Bearer real-token")
        r = c.get("/api/v1/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["status"] == "NEW" and body["next_step"] == "CHOOSE_ROLE"
    assert User.objects.get(firebase_uid="fb-123").email == "new.person@example.com"


@pytest.mark.django_db
def test_firebase_token_links_preprovisioned_user(world):
    claims = {"uid": "fb-owner", "email": "owner@test.io", "email_verified": True}
    with mock.patch("apps.core.authentication.verify_firebase_token", return_value=claims):
        c = world.client()
        c.credentials(HTTP_AUTHORIZATION="Bearer real-token")
        assert c.get("/api/v1/auth/me").json()["next_step"] == "APP"
    world.owner.refresh_from_db()
    assert world.owner.firebase_uid == "fb-owner"


@pytest.mark.django_db
def test_unverified_email_does_not_link_existing_account(world):
    claims = {"uid": "fb-attacker", "email": "owner@test.io", "email_verified": False}
    with mock.patch("apps.core.authentication.verify_firebase_token", return_value=claims):
        c = world.client()
        c.credentials(HTTP_AUTHORIZATION="Bearer t")
        assert c.get("/api/v1/auth/me").status_code == 401


@pytest.mark.django_db
def test_invalid_firebase_token_is_401(world):
    with mock.patch("apps.core.authentication.verify_firebase_token", side_effect=ValueError("bad")):
        c = world.client()
        c.credentials(HTTP_AUTHORIZATION="Bearer junk")
        assert c.get("/api/v1/auth/me").status_code == 401


ENDPOINTS_REQUIRING_APPROVAL = ["/api/v1/port-calls", "/api/v1/requests", "/api/v1/dashboard", "/api/v1/vendor-invoices",
                                "/api/v1/chat/threads", "/api/v1/meta/enums", "/api/v1/agents", "/api/v1/fx-rates", "/api/v1/vessels"]


@pytest.mark.django_db
@pytest.mark.parametrize("url", ENDPOINTS_REQUIRING_APPROVAL)
def test_unapproved_users_blocked_server_side(world, url):
    pending = User.objects.create(email="pending@test.io", firebase_uid="dev-pending@test.io")
    r = world.client(pending).get(url)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "not_approved"
    assert r.json()["error"]["details"]["next_step"] == "CHOOSE_ROLE"


@pytest.mark.django_db
def test_suspended_org_blocks_its_users(world):
    from apps.accounts.services import suspend_organization

    suspend_organization(actor=world.admin, organization=world.agent_org, reason="KYC expired")
    r = world.client(world.agent).get("/api/v1/port-calls")
    assert r.status_code == 403 and r.json()["error"]["details"]["next_step"] == "SUSPENDED"


@pytest.mark.django_db
def test_onboarding_flow_then_admin_approval(world):
    from conftest import pdf_upload

    newbie = User.objects.create(email="newbie@test.io")
    c = world.client(newbie)
    assert c.post("/api/v1/auth/choose-role", {"role": "AGENT"}, format="json").status_code == 201
    r = c.post("/api/v1/onboarding/submit")
    assert r.status_code == 400 and "documents" in r.json()["error"]["details"]["missing"]
    c.put("/api/v1/onboarding/organization", {"legal_name": "Newbie Agency", "country_code": "IN", "city": "Mumbai"}, format="json")
    c.put("/api/v1/onboarding/profile", {"description": "We agent ships.", "default_agency_fee": {"amount": "800.00", "currency_code": "USD"}}, format="json")
    from conftest import svc

    r = c.put("/api/v1/onboarding/coverage", {"port_ids": [world.port.pk], "service_category_ids": [svc("PILOTAGE").pk]}, format="json")
    assert r.status_code == 200, r.json()
    r = c.post("/api/v1/onboarding/documents", {"document_type": "COMPANY_REGISTRATION", "file": pdf_upload()}, format="multipart")
    assert r.status_code == 201, r.json()
    assert c.post("/api/v1/onboarding/submit").json()["next_step"] == "PENDING_REVIEW"
    assert c.get("/api/v1/port-calls").status_code == 403  # still blocked
    admin = world.client(world.admin)
    newbie.refresh_from_db()
    assert admin.post(f"/api/v1/admin/users/{newbie.pk}/approve", {}, format="json").status_code == 200
    assert c.get("/api/v1/port-calls").status_code == 200
    assert c.get("/api/v1/auth/me").json()["organization_status"] == "APPROVED"


@pytest.mark.django_db
def test_rejected_user_can_resubmit(world):
    from apps.accounts import services as acc

    u = User.objects.create(email="rej@test.io")
    acc.choose_role(user=u, role="OWNER", legal_name="Rej Shipping")
    acc.update_organization(user=u, data={"legal_name": "Rej Shipping Ltd"})
    acc.update_coverage(user=u, port_ids=[world.port.pk])
    from apps.documents.services import store_bytes
    from conftest import PDF_BYTES

    f = store_bytes(data=PDF_BYTES, filename="a.pdf", content_type="application/pdf", purpose="VERIFICATION", user=u)
    acc.add_verification_document(user=u, document_type="OTHER", title="", file=f)
    acc.submit_onboarding(user=u)
    acc.reject_user(actor=world.admin, user=u, reason="Blurry certificate")
    u.refresh_from_db()
    assert u.status == UserStatus.REJECTED and u.organization.verification_status == "REJECTED"
    acc.update_organization(user=u, data={"tax_id": "X1"})  # first edit performs `resubmit`
    u.refresh_from_db()
    assert u.status == UserStatus.ONBOARDING and u.organization.verification_status == "DRAFT"
    acc.submit_onboarding(user=u)


ROLE_GATES = [
    # (method, url template, user attr, expected status)
    ("post", "/api/v1/port-calls/{pc}/pda", "owner", 404),
    ("post", "/api/v1/disbursement-accounts/{pda}/issue", "owner", 403),
    ("post", "/api/v1/disbursement-accounts/{pda}/approve", "agent", 403),
    ("post", "/api/v1/disbursement-accounts/{pda}/issue", "merchant", 403),
    ("post", "/api/v1/port-calls/{pc}/arrive", "owner", 403),
    ("get", "/api/v1/admin/users", "agent", 403),
    ("get", "/api/v1/vessels", "agent", 403),
    ("get", "/api/v1/fx-rates", "owner", 403),
    ("get", "/api/v1/agents", "merchant", 403),
    ("post", "/api/v1/vendor-invoices", "agent", 404),
]


@pytest.mark.django_db
@pytest.mark.parametrize("method,url,who,expected", ROLE_GATES)
def test_role_gates(world, method, url, who, expected):
    out = world.stage("PDA_PENDING")
    url = url.format(pc=out["pc"].pk, pda=out["pda"].pk)
    c = world.client(getattr(world, who))
    r = getattr(c, method)(url, {}, format="json")
    assert r.status_code == expected, r.content


@pytest.mark.django_db
def test_object_scoping_returns_404_for_other_parties(world):
    out = world.stage("PDA_SENT")
    pc = out["pc"]
    for outsider in (world.owner2, world.agent2, world.merchant2):
        assert world.client(outsider).get(f"/api/v1/port-calls/{pc.pk}").status_code == 404
    assert world.client(world.owner2).get(f"/api/v1/disbursement-accounts/{out['pda'].pk}").status_code == 404
    assert world.client(world.agent2).post(f"/api/v1/disbursement-accounts/{out['pda'].pk}/approve", {}, format="json").status_code == 403
    assert world.client(world.owner2).get("/api/v1/port-calls").json()["count"] == 0
    assert world.client(world.owner).get("/api/v1/port-calls").json()["count"] == 1


@pytest.mark.django_db
def test_merchant_sees_call_only_after_accepting_and_without_financials(world):
    out = world.stage("IN_PORT")
    pc = out["pc"]
    r = world.client(world.merchant).get(f"/api/v1/port-calls/{pc.pk}")
    assert r.status_code == 200
    body = r.json()
    assert "pda" not in body and "advance_total" not in body and "owner" not in body
    assert world.client(world.merchant).get(f"/api/v1/port-calls/{pc.pk}/pda").status_code == 403
    assert world.client(world.merchant2).get(f"/api/v1/port-calls/{pc.pk}").status_code == 404


@pytest.mark.django_db
def test_request_policy_layer(world):
    from apps.requests.models import RequestRolePolicy

    c = world.client(world.merchant)
    payload = {"request_type": "VENDOR_SERVICE", "to_organization_id": world.agent_org.pk, "port_call_id": world.port_call().pk}
    r = c.post("/api/v1/requests", payload, format="json")
    assert r.status_code == 403 and r.json()["error"]["code"] == "policy_denied"
    # Owner → Agent is enabled; disabling the row closes that direction without code changes.
    RequestRolePolicy.objects.filter(request_type="PORT_CALL", from_role="OWNER", to_role="AGENT").update(is_enabled=False)
    r = world.client(world.owner).post("/api/v1/requests", {
        "request_type": "PORT_CALL", "to_organization_id": world.agent_org.pk,
        "details": {"vessel_id": world.vessel.pk, "port_id": world.port.pk, "eta": "2030-01-01T00:00:00Z", "etd": "2030-01-02T00:00:00Z",
                    "cargo_type_id": world.cargo.pk}}, format="json")
    assert r.status_code == 403 and r.json()["error"]["code"] == "policy_denied"


@pytest.mark.django_db
def test_admin_cannot_chat_and_owner_merchant_never_share_thread(world):
    from apps.chat.models import ChatThread

    world.stage("IN_PORT")
    for thread in ChatThread.objects.all():
        types = set(thread.participants.values_list("organization__type", flat=True))
        assert not {"OWNER", "MERCHANT"} <= types
    assert world.client(world.admin).get("/api/v1/chat/threads").status_code == 403
    assert world.client(world.owner).get("/api/v1/chat/threads").json()["count"] == 1
    assert world.client(world.merchant).get("/api/v1/chat/threads").json()["count"] == 1
    assert world.client(world.agent).get("/api/v1/chat/threads").json()["count"] == 2


@pytest.mark.django_db
def test_merchant_discovery_for_agents(world):
    from conftest import svc

    r = world.client(world.agent).get(f"/api/v1/merchants?port_id={world.port.pk}&service_category_id={svc('PILOTAGE').pk}")
    assert r.status_code == 200 and [m["legal_name"] for m in r.json()["results"]] == ["Pilots Co"]
    assert world.client(world.owner).get("/api/v1/merchants").status_code == 403


@pytest.mark.django_db
def test_reference_data_readable_during_onboarding(world):
    pending = User.objects.create(email="onb@test.io")
    for url in ("/api/v1/ports", "/api/v1/locations", "/api/v1/countries", "/api/v1/service-categories", "/api/v1/currencies", "/api/v1/cargo-types"):
        assert world.client(pending).get(url).status_code == 200


def _claims(**over):
    base = {"iss": "https://securetoken.google.com/proj-1", "aud": "proj-1", "sub": "uid-1", "email": "a@b.co", "email_verified": True}
    return {**base, **over}


def test_token_verification_checks_issuer_and_project(settings):
    from apps.core import authentication

    settings.FIREBASE_PROJECT_ID = "proj-1"
    settings.FIREBASE_SERVICE_ACCOUNT_JSON_BASE64 = ""
    with mock.patch("google.oauth2.id_token.verify_firebase_token", return_value=_claims()) as verify:
        claims = authentication.verify_firebase_token("t")
    assert claims["uid"] == "uid-1"
    assert verify.call_args.kwargs["audience"] == "proj-1"  # audience is enforced by google-auth
    with mock.patch("google.oauth2.id_token.verify_firebase_token", return_value=_claims(iss="https://securetoken.google.com/other")):
        with pytest.raises(ValueError):
            authentication.verify_firebase_token("t")
    with mock.patch("google.oauth2.id_token.verify_firebase_token", return_value=_claims(sub="")):
        with pytest.raises(ValueError):
            authentication.verify_firebase_token("t")
    settings.FIREBASE_PROJECT_ID = ""
    with pytest.raises(ValueError):
        authentication.verify_firebase_token("t")
