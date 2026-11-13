from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.enums import AccountKind, AccountStatus, check_in
from apps.core.models import TimeStampedModel


class DisbursementAccount(TimeStampedModel):
    """PDA and FDA share one structure (SCHEMA.md D7)."""

    port_call = models.ForeignKey("portcalls.PortCall", on_delete=models.PROTECT, related_name="accounts")
    kind = models.CharField(max_length=3, choices=AccountKind.choices)
    version = models.SmallIntegerField(default=1)
    is_current = models.BooleanField(default=True)
    reference = models.CharField(max_length=32, unique=True)
    status = models.CharField(max_length=16, choices=AccountStatus.choices, default=AccountStatus.DRAFT)
    currency = models.ForeignKey("masterdata.Currency", on_delete=models.PROTECT, db_column="currency_code", related_name="+")
    total_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)  # denormalized (D16)
    supersedes = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="superseded_by")
    prepared_by_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    issued_at = models.DateTimeField(null=True, blank=True)
    owner_responded_by_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    owner_responded_at = models.DateTimeField(null=True, blank=True)
    owner_response_note = models.TextField(default="", blank=True)
    finalized_at = models.DateTimeField(null=True, blank=True)
    fx_policy_note = models.TextField(default="", blank=True)
    notes = models.TextField(default="", blank=True)

    class Meta:
        db_table = "disbursement_accounts"
        indexes = [models.Index(fields=["port_call", "kind", "is_current"], name="account_pc_kind_current_idx")]
        constraints = [
            models.CheckConstraint(condition=check_in("kind", AccountKind), name="account_kind_chk"),
            models.CheckConstraint(condition=check_in("status", AccountStatus), name="account_status_chk"),
            models.CheckConstraint(condition=Q(version__gte=1), name="account_version_chk"),
            models.UniqueConstraint(fields=["port_call", "kind", "version"], name="account_pc_kind_version_uniq"),
            models.UniqueConstraint(fields=["port_call", "kind"], condition=Q(is_current=True), name="account_one_current_uniq"),
            models.CheckConstraint(
                condition=Q(kind=AccountKind.PDA) | ~Q(status__in=[AccountStatus.APPROVED, AccountStatus.REJECTED]),
                name="account_pda_only_approval_chk",
            ),
            models.CheckConstraint(condition=Q(kind=AccountKind.FDA) | ~Q(status=AccountStatus.FINAL), name="account_fda_only_final_chk"),
            models.CheckConstraint(
                condition=Q(version=1, supersedes__isnull=True) | Q(version__gt=1, supersedes__isnull=False),
                name="account_version_chain_chk",
            ),
        ]

    def __str__(self):
        return self.reference


class DisbursementLineItem(TimeStampedModel):
    account = models.ForeignKey(DisbursementAccount, on_delete=models.CASCADE, related_name="line_items")
    line_no = models.SmallIntegerField()
    service_category = models.ForeignKey("masterdata.ServiceCategory", on_delete=models.PROTECT, related_name="+")
    description = models.CharField(max_length=300)
    vendor_organization = models.ForeignKey("accounts.Organization", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=1)
    unit = models.CharField(max_length=16, default="lot", blank=True)
    local_amount = models.DecimalField(max_digits=18, decimal_places=2)
    local_currency = models.ForeignKey("masterdata.Currency", on_delete=models.PROTECT, db_column="local_currency_code", related_name="+")
    fx_rate = models.ForeignKey("masterdata.FxRate", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    fx_rate_applied = models.DecimalField(max_digits=20, decimal_places=10, default=1)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    pda_line_item = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="fda_lines")
    vendor_invoice = models.ForeignKey("invoices.VendorInvoice", null=True, blank=True, on_delete=models.PROTECT, related_name="fda_lines")
    supersedes_line_item = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="superseded_by")
    is_adjustment = models.BooleanField(default=False)
    source_dispute = models.ForeignKey("disputes.Dispute", null=True, blank=True, on_delete=models.PROTECT, related_name="adjustment_lines")
    notes = models.TextField(default="", blank=True)

    class Meta:
        db_table = "disbursement_line_items"
        ordering = ["line_no"]
        indexes = [
            models.Index(fields=["pda_line_item"], name="line_pda_line_idx"),
            models.Index(fields=["vendor_invoice"], name="line_vendor_invoice_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["account", "line_no"], name="line_account_line_no_uniq"),
            models.UniqueConstraint(
                fields=["account", "vendor_invoice"], condition=Q(vendor_invoice__isnull=False), name="line_account_invoice_uniq"
            ),
            models.CheckConstraint(
                condition=Q(fx_rate__isnull=True, fx_rate_applied=1) | Q(fx_rate__isnull=False, fx_rate_applied__gt=0),
                name="line_fx_provenance_chk",
            ),
            models.CheckConstraint(condition=Q(is_adjustment=True) | Q(local_amount__gte=0), name="line_nonneg_unless_adjustment_chk"),
            models.CheckConstraint(
                condition=Q(is_adjustment=True, source_dispute__isnull=False) | Q(is_adjustment=False, source_dispute__isnull=True),
                name="line_adjustment_source_chk",
            ),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="line_quantity_positive_chk"),
        ]
