from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.core.enums import PortCallStatus, check_in
from apps.core.models import TimeStampedModel


class PortCall(TimeStampedModel):
    """Central aggregate (SCHEMA.md D6)."""

    reference = models.CharField(max_length=24, unique=True)
    request = models.OneToOneField("requests.Request", on_delete=models.PROTECT, related_name="created_port_call")
    owner_organization = models.ForeignKey("accounts.Organization", on_delete=models.PROTECT, related_name="owned_port_calls")
    agent_organization = models.ForeignKey("accounts.Organization", on_delete=models.PROTECT, related_name="agent_port_calls")
    vessel = models.ForeignKey("vessels.Vessel", on_delete=models.PROTECT, related_name="port_calls")
    port = models.ForeignKey("masterdata.Port", on_delete=models.PROTECT, related_name="port_calls")
    cargo_type = models.ForeignKey("masterdata.CargoType", on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=24, choices=PortCallStatus.choices, default=PortCallStatus.PDA_PENDING)
    settlement_currency = models.ForeignKey(
        "masterdata.Currency", on_delete=models.PROTECT, db_column="settlement_currency_code", default="USD", related_name="+"
    )
    eta = models.DateTimeField()
    etd = models.DateTimeField()
    ata = models.DateTimeField(null=True, blank=True)
    atd = models.DateTimeField(null=True, blank=True)
    berth = models.CharField(max_length=100, default="", blank=True)
    notes = models.TextField(default="", blank=True)
    cancelled_reason = models.TextField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    status_changed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "port_calls"
        indexes = [
            models.Index(fields=["agent_organization", "status"], name="pc_agent_status_idx"),
            models.Index(fields=["owner_organization", "status"], name="pc_owner_status_idx"),
            models.Index(fields=["vessel"], name="pc_vessel_idx"),
            models.Index(fields=["port", "eta"], name="pc_port_eta_idx"),
            models.Index(fields=["status", "eta"], name="pc_status_eta_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=check_in("status", PortCallStatus), name="pc_status_chk"),
            models.CheckConstraint(condition=Q(etd__gt=F("eta")), name="pc_etd_after_eta_chk"),
            models.CheckConstraint(condition=Q(atd__isnull=True) | Q(ata__isnull=False), name="pc_atd_requires_ata_chk"),
            models.CheckConstraint(condition=Q(atd__isnull=True) | Q(atd__gte=F("ata")), name="pc_atd_after_ata_chk"),
        ]

    def __str__(self):
        return self.reference
