from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from apps.core.enums import VesselType, check_in
from apps.core.models import TimeStampedModel


class Vessel(TimeStampedModel):
    owner_organization = models.ForeignKey("accounts.Organization", on_delete=models.PROTECT, related_name="vessels")
    name = models.CharField(max_length=150)
    imo_number = models.CharField(max_length=7, null=True, blank=True)
    call_sign = models.CharField(max_length=16, default="", blank=True)
    flag_country = models.ForeignKey(
        "masterdata.Country", null=True, blank=True, on_delete=models.PROTECT, db_column="flag_country_code", related_name="+"
    )
    vessel_type = models.CharField(max_length=32, choices=VesselType.choices)
    grt = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    nrt = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    dwt = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    loa_m = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    beam_m = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    max_draft_m = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "vessels"
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(condition=Q(imo_number__isnull=True) | Q(imo_number__regex=r"^[0-9]{7}$"), name="vessel_imo_format_chk"),
            models.UniqueConstraint(
                fields=["imo_number"], condition=Q(imo_number__isnull=False, deleted_at__isnull=True), name="vessel_imo_uniq"
            ),
            models.UniqueConstraint("owner_organization", Lower("name"), condition=Q(deleted_at__isnull=True), name="vessel_owner_name_uniq"),
            models.CheckConstraint(condition=check_in("vessel_type", VesselType), name="vessel_type_chk"),
            *[
                models.CheckConstraint(condition=Q(**{f"{f}__isnull": True}) | Q(**{f"{f}__gte": 0}), name=f"vessel_{f}_nonneg_chk")
                for f in ("grt", "nrt", "dwt", "loa_m", "beam_m", "max_draft_m")
            ],
        ]

    def __str__(self):
        return self.name
