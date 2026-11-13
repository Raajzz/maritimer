from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.core.enums import InvoiceStatus, check_in
from apps.core.models import TimeStampedModel


class VendorInvoice(TimeStampedModel):
    port_call = models.ForeignKey("portcalls.PortCall", on_delete=models.PROTECT, related_name="vendor_invoices")
    vendor_organization = models.ForeignKey("accounts.Organization", on_delete=models.PROTECT, related_name="issued_invoices")
    agent_organization = models.ForeignKey("accounts.Organization", on_delete=models.PROTECT, related_name="received_invoices")
    vendor_request = models.ForeignKey("requests.Request", null=True, blank=True, on_delete=models.PROTECT, related_name="invoices")
    service_category = models.ForeignKey("masterdata.ServiceCategory", on_delete=models.PROTECT, related_name="+")
    invoice_number = models.CharField(max_length=60)
    issue_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    currency = models.ForeignKey("masterdata.Currency", on_delete=models.PROTECT, db_column="currency_code", related_name="+")
    subtotal_amount = models.DecimalField(max_digits=18, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=18, decimal_places=2)
    status = models.CharField(max_length=16, choices=InvoiceStatus.choices, default=InvoiceStatus.DRAFT)
    file = models.ForeignKey("documents.StoredFile", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    submitted_by_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    reviewed_by_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(default="", blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(default="", blank=True)

    class Meta:
        db_table = "vendor_invoices"
        indexes = [
            models.Index(fields=["port_call", "status"], name="invoice_pc_status_idx"),
            models.Index(fields=["agent_organization", "status"], name="invoice_agent_status_idx"),
            models.Index(fields=["vendor_organization", "status"], name="invoice_vendor_status_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["vendor_organization", "invoice_number"], name="invoice_vendor_number_uniq"),
            models.CheckConstraint(condition=check_in("status", InvoiceStatus), name="invoice_status_chk"),
            models.CheckConstraint(condition=Q(subtotal_amount__gte=0), name="invoice_subtotal_nonneg_chk"),
            models.CheckConstraint(condition=Q(tax_amount__gte=0), name="invoice_tax_nonneg_chk"),
            models.CheckConstraint(condition=Q(total_amount=F("subtotal_amount") + F("tax_amount")), name="invoice_total_chk"),
        ]

    def __str__(self):
        return self.invoice_number


class VendorInvoiceLine(TimeStampedModel):
    invoice = models.ForeignKey(VendorInvoice, on_delete=models.CASCADE, related_name="lines")
    line_no = models.SmallIntegerField()
    description = models.CharField(max_length=300)
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=1)
    unit = models.CharField(max_length=16, default="", blank=True)
    unit_amount = models.DecimalField(max_digits=18, decimal_places=2)
    amount = models.DecimalField(max_digits=18, decimal_places=2)

    class Meta:
        db_table = "vendor_invoice_lines"
        ordering = ["line_no"]
        constraints = [
            models.UniqueConstraint(fields=["invoice", "line_no"], name="invoice_line_no_uniq"),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="invoice_line_qty_chk"),
            models.CheckConstraint(condition=Q(unit_amount__gte=0), name="invoice_line_unit_chk"),
            models.CheckConstraint(condition=Q(amount__gte=0), name="invoice_line_amount_chk"),
        ]
