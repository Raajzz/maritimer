"""Database-level invariants from SCHEMA.md §4 plus the service-enforced cross-table rules."""
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.accounts.models import AgentProfile, MerchantProfile, OwnerProfile
from apps.core.enums import AccountKind
from apps.core.models import AuditLog
from apps.payments.models import Payment, Settlement


def raises_integrity(fn):
    with pytest.raises(IntegrityError), transaction.atomic():
        fn()


@pytest.mark.django_db
def test_profile_type_matches_organization(world):
    assert OwnerProfile.objects.filter(organization=world.owner_org).exists()
    assert AgentProfile.objects.filter(organization=world.agent_org).exists()
    assert MerchantProfile.objects.filter(organization=world.merchant_org).exists()
    assert not AgentProfile.objects.filter(organization=world.owner_org).exists()


@pytest.mark.django_db
def test_one_org_per_user(world):
    from apps.accounts.models import OrganizationMember

    raises_integrity(lambda: OrganizationMember.objects.create(organization=world.agent_org, user=world.owner, is_primary_contact=False))


@pytest.mark.django_db
def test_one_current_account_per_kind(world):
    from apps.disbursements.models import DisbursementAccount

    out = world.stage("PDA_PENDING")
    raises_integrity(lambda: DisbursementAccount.objects.create(
        port_call=out["pc"], kind=AccountKind.PDA, version=2, supersedes=out["pda"], reference="X", currency_id="USD", prepared_by_user=world.agent))


@pytest.mark.django_db
def test_line_fx_provenance_check(world):
    from apps.disbursements.models import DisbursementLineItem

    out = world.stage("PDA_PENDING")
    line = out["pda"].line_items.filter(fx_rate__isnull=False).first()
    raises_integrity(lambda: DisbursementLineItem.objects.filter(pk=line.pk).update(fx_rate=None))


@pytest.mark.django_db
def test_negative_amount_only_on_adjustments(world):
    out = world.stage("PDA_PENDING")
    line = out["pda"].line_items.first()
    raises_integrity(lambda: type(line).objects.filter(pk=line.pk).update(local_amount=Decimal("-1")))


@pytest.mark.django_db
def test_settlement_checks(world):
    out = world.stage("FDA_FINAL", advance="1500.00")
    s = out["settlement"]
    raises_integrity(lambda: Settlement.objects.filter(pk=s.pk).update(direction="REFUND_DUE"))
    raises_integrity(lambda: Settlement.objects.filter(pk=s.pk).update(balance=Decimal("1.00")))
    raises_integrity(lambda: Settlement.objects.filter(pk=s.pk).update(status="CLOSED"))  # closed_at missing


@pytest.mark.django_db
def test_payment_kind_links(world):
    out = world.stage("ADVANCE_RECEIVED")
    p = out["advance"]
    raises_integrity(lambda: Payment.objects.filter(pk=p.pk).update(disbursement_account=None))
    raises_integrity(lambda: Payment.objects.filter(pk=p.pk).update(confirmed_at=None))
    raises_integrity(lambda: Payment.objects.filter(pk=p.pk).update(payee_organization=p.payer_organization))


@pytest.mark.django_db
def test_invoice_total_check_and_unique_number(world):
    from apps.invoices.models import VendorInvoice

    out = world.stage("IN_PORT")
    inv = out["invoice"]
    raises_integrity(lambda: VendorInvoice.objects.filter(pk=inv.pk).update(total_amount=Decimal("1")))
    from apps.core.exceptions import ValidationFailed
    from apps.invoices.services import create_invoice

    with pytest.raises(ValidationFailed):
        create_invoice(actor=world.merchant, data={"port_call_id": out["pc"].pk, "vendor_request_id": out["vendor_request"].pk,
                                                  "service_category_id": inv.service_category_id, "invoice_number": inv.invoice_number,
                                                  "issue_date": world.now.date(), "currency_code": "INR", "subtotal_amount": Decimal("1"),
                                                  "tax_amount": Decimal("0"), "total_amount": Decimal("1")})


@pytest.mark.django_db
def test_audit_log_is_append_only_and_written_per_transition(world):
    out = world.stage("PDA_APPROVED")
    entry = AuditLog.objects.filter(port_call=out["pc"]).first()
    with pytest.raises(RuntimeError):
        entry.save()
    actions = list(AuditLog.objects.filter(port_call=out["pc"]).order_by("id").values_list("action", flat=True))
    for expected in ("request.accepted", "port_call.created", "pda.created", "pda.issued", "port_call.pda_sent", "pda.approved", "port_call.pda_approved"):
        assert expected in actions
    sent = AuditLog.objects.get(port_call=out["pc"], action="port_call.pda_sent")
    assert (sent.from_state, sent.to_state, sent.actor_user_id) == ("PDA_PENDING", "PDA_SENT", world.agent.pk)


@pytest.mark.django_db
def test_invoice_requires_accepted_vendor_request(world):
    from apps.core.exceptions import Forbidden
    from apps.invoices.services import create_invoice

    out = world.stage("ADVANCE_RECEIVED")
    with pytest.raises(Forbidden):
        create_invoice(actor=world.merchant2, data={"port_call_id": out["pc"].pk, "vendor_request_id": None, "service_category_id": 1,
                                                   "invoice_number": "Z", "issue_date": world.now.date(), "currency_code": "INR",
                                                   "subtotal_amount": Decimal("1"), "total_amount": Decimal("1")})


@pytest.mark.django_db
def test_cancel_voids_pda_withdraws_requests_and_closes_chat(world):
    from apps.chat.models import ChatThread
    from apps.portcalls.services import cancel
    from apps.requests import services as req
    from conftest import svc

    out = world.stage("PDA_APPROVED")
    pc = out["pc"]
    r = req.create_request(actor=world.agent, data={"request_type": "VENDOR_SERVICE", "to_organization_id": world.merchant_org.pk,
                                                    "port_call_id": pc.pk, "services": [{"service_category_id": svc("PILOTAGE").pk}]})
    from apps.core.exceptions import Forbidden

    with pytest.raises(Forbidden):  # owners may cancel only before PDA approval
        cancel(actor=world.owner, port_call=pc, reason="changed plans")
    cancel(actor=world.agent, port_call=pc, reason="Voyage cancelled")
    pc.refresh_from_db(); out["pda"].refresh_from_db(); r.refresh_from_db()
    assert pc.status == "CANCELLED" and out["pda"].status == "VOID" and r.status == "WITHDRAWN"
    assert not ChatThread.objects.filter(port_call=pc, is_closed=False).exists()
