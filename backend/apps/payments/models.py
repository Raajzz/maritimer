from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.core.enums import (
    PaymentKind,
    PaymentMethod,
    PaymentStatus,
    SettlementDirection,
    SettlementStatus,
    check_in,
)
from apps.core.models import TimeStampedModel


class Payment(TimeStampedModel):
    reference = models.CharField(max_length=24, unique=True)
    port_call = models.ForeignKey("portcalls.PortCall", on_delete=models.PROTECT, related_name="payments")
    kind = models.CharField(max_length=16, choices=PaymentKind.choices)
    payer_organization = models.ForeignKey("accounts.Organization", on_delete=models.PROTECT, related_name="+")
    payee_organization = models.ForeignKey("accounts.Organization", on_delete=models.PROTECT, related_name="+")
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.ForeignKey("masterdata.Currency", on_delete=models.PROTECT, db_column="currency_code", related_name="+")
    fx_rate = models.ForeignKey("masterdata.FxRate", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    fx_rate_applied = models.DecimalField(max_digits=20, decimal_places=10, default=1)
    settlement_amount = models.DecimalField(max_digits=18, decimal_places=2)
    disbursement_account = models.ForeignKey(
        "disbursements.DisbursementAccount", null=True, blank=True, on_delete=models.PROTECT, related_name="payments"
    )
    settlement = models.ForeignKey("payments.Settlement", null=True, blank=True, on_delete=models.PROTECT, related_name="payments")
    vendor_invoice = models.ForeignKey("invoices.VendorInvoice", null=True, blank=True, on_delete=models.PROTECT, related_name="payments")
    status = models.CharField(max_length=16, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    method = models.CharField(max_length=24, choices=PaymentMethod.choices, default=PaymentMethod.BANK_TRANSFER)
    bank_reference = models.CharField(max_length=120, default="", blank=True)
    provider = models.CharField(max_length=32, default="MANUAL")
    provider_reference = models.CharField(max_length=200, default="", blank=True)
    provider_payload = models.JSONField(default=dict, blank=True)
    paid_at = models.DateTimeField()
    recorded_by_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    confirmed_by_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    confirmed_at = models.DateTimeField(null=True, blank=True)
    cancelled_reason = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "payments"
        indexes = [
            models.Index(fields=["port_call", "kind", "status"], name="payment_pc_kind_status_idx"),
            models.Index(fields=["settlement"], name="payment_settlement_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=check_in("kind", PaymentKind), name="payment_kind_chk"),
            models.CheckConstraint(condition=check_in("status", PaymentStatus), name="payment_status_chk"),
            models.CheckConstraint(condition=check_in("method", PaymentMethod), name="payment_method_chk"),
            models.CheckConstraint(condition=Q(amount__gt=0), name="payment_amount_positive_chk"),
            models.CheckConstraint(condition=~Q(payer_organization=F("payee_organization")), name="payment_distinct_parties_chk"),
            models.CheckConstraint(
                condition=~Q(kind=PaymentKind.ADVANCE) | Q(disbursement_account__isnull=False), name="payment_advance_account_chk"
            ),
            models.CheckConstraint(
                condition=~Q(kind__in=[PaymentKind.BALANCE, PaymentKind.REFUND]) | Q(settlement__isnull=False),
                name="payment_settlement_link_chk",
            ),
            models.CheckConstraint(
                condition=~Q(kind=PaymentKind.VENDOR_PAYMENT) | Q(vendor_invoice__isnull=False), name="payment_vendor_invoice_chk"
            ),
            models.CheckConstraint(
                condition=Q(status=PaymentStatus.CONFIRMED, confirmed_at__isnull=False)
                | (~Q(status=PaymentStatus.CONFIRMED) & Q(confirmed_at__isnull=True)),
                name="payment_confirmed_at_chk",
            ),
            models.CheckConstraint(
                condition=Q(fx_rate__isnull=True, fx_rate_applied=1) | Q(fx_rate__isnull=False, fx_rate_applied__gt=0),
                name="payment_fx_provenance_chk",
            ),
        ]


class Settlement(TimeStampedModel):
    """Immutable snapshot created by FDA finalization (SCHEMA.md D10)."""

    reference = models.CharField(max_length=24, unique=True)
    port_call = models.OneToOneField("portcalls.PortCall", on_delete=models.PROTECT, related_name="settlement")
    fda = models.OneToOneField("disbursements.DisbursementAccount", on_delete=models.PROTECT, related_name="settlement")
    pda = models.ForeignKey("disbursements.DisbursementAccount", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    currency = models.ForeignKey("masterdata.Currency", on_delete=models.PROTECT, db_column="currency_code", related_name="+")
    pda_total = models.DecimalField(max_digits=18, decimal_places=2)
    fda_total = models.DecimalField(max_digits=18, decimal_places=2)
    advance_total = models.DecimalField(max_digits=18, decimal_places=2)
    balance = models.DecimalField(max_digits=18, decimal_places=2)
    direction = models.CharField(max_length=16, choices=SettlementDirection.choices)
    status = models.CharField(max_length=16, choices=SettlementStatus.choices, default=SettlementStatus.OPEN)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        db_table = "settlements"
        constraints = [
            models.CheckConstraint(condition=check_in("direction", SettlementDirection), name="settlement_direction_chk"),
            models.CheckConstraint(condition=check_in("status", SettlementStatus), name="settlement_status_chk"),
            models.CheckConstraint(
                condition=Q(balance__gt=0, direction=SettlementDirection.BALANCE_DUE)
                | Q(balance__lt=0, direction=SettlementDirection.REFUND_DUE)
                | Q(balance=0, direction=SettlementDirection.NIL),
                name="settlement_direction_sign_chk",
            ),
            models.CheckConstraint(condition=Q(balance=F("fda_total") - F("advance_total")), name="settlement_balance_chk"),
            models.CheckConstraint(
                condition=Q(status=SettlementStatus.CLOSED, closed_at__isnull=False)
                | (~Q(status=SettlementStatus.CLOSED) & Q(closed_at__isnull=True)),
                name="settlement_closed_at_chk",
            ),
        ]
