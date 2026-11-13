from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower

from apps.core.enums import FxSource, check_in
from apps.core.models import TimeStampedModel


class Country(TimeStampedModel):
    code = models.CharField(max_length=2, primary_key=True)
    iso3 = models.CharField(max_length=3, unique=True)
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "countries"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Location(TimeStampedModel):
    country = models.ForeignKey(Country, on_delete=models.PROTECT, db_column="country_code", related_name="locations")
    name = models.CharField(max_length=120)
    region = models.CharField(max_length=120, default="", blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "locations"
        ordering = ["name"]
        constraints = [models.UniqueConstraint("country", Lower("name"), name="location_country_name_uniq")]

    def __str__(self):
        return self.name


class Port(TimeStampedModel):
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="ports")
    name = models.CharField(max_length=150)
    unlocode = models.CharField(max_length=5, null=True, blank=True)
    timezone = models.CharField(max_length=64)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "ports"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint("location", Lower("name"), name="port_location_name_uniq"),
            models.UniqueConstraint(fields=["unlocode"], condition=Q(unlocode__isnull=False), name="port_unlocode_uniq"),
        ]

    def __str__(self):
        return self.name


class ServiceCategory(TimeStampedModel):
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(default="", blank=True)
    is_vendor_service = models.BooleanField(default=True)
    is_agent_fee = models.BooleanField(default=False)
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "service_categories"
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["is_agent_fee"], condition=Q(is_agent_fee=True), name="service_one_agent_fee_uniq"),
        ]

    def __str__(self):
        return self.name


class CargoType(TimeStampedModel):
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "cargo_types"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Currency(TimeStampedModel):
    code = models.CharField(max_length=3, primary_key=True)
    name = models.CharField(max_length=60)
    symbol = models.CharField(max_length=8, default="", blank=True)
    minor_units = models.SmallIntegerField(default=2)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "currencies"
        ordering = ["code"]
        constraints = [models.CheckConstraint(condition=Q(minor_units__gte=0, minor_units__lte=4), name="currency_minor_units_chk")]

    def __str__(self):
        return self.code


class FxRate(models.Model):
    """Append-only. `rate` = quote units per 1 base unit (INR→USD ≈ 0.012)."""

    base_currency = models.ForeignKey(Currency, on_delete=models.PROTECT, db_column="base_currency_code", related_name="+")
    quote_currency = models.ForeignKey(Currency, on_delete=models.PROTECT, db_column="quote_currency_code", related_name="+")
    rate = models.DecimalField(max_digits=20, decimal_places=10)
    source = models.CharField(max_length=32, choices=FxSource.choices, default=FxSource.MANUAL)
    source_reference = models.CharField(max_length=200, default="", blank=True)
    as_of = models.DateTimeField()
    fetched_at = models.DateTimeField(auto_now_add=True)
    created_by_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "fx_rates"
        ordering = ["-as_of", "-id"]
        indexes = [models.Index(fields=["base_currency", "quote_currency", "-as_of"], name="fx_pair_asof_idx")]
        constraints = [
            models.CheckConstraint(condition=Q(rate__gt=0), name="fx_rate_positive_chk"),
            models.CheckConstraint(condition=~Q(base_currency=F("quote_currency")), name="fx_distinct_pair_chk"),
            models.CheckConstraint(condition=check_in("source", FxSource), name="fx_source_chk"),
            models.UniqueConstraint(fields=["base_currency", "quote_currency", "source", "as_of"], name="fx_pair_source_asof_uniq"),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise RuntimeError("fx_rates is append-only; create a new row instead")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"1 {self.base_currency_id} = {self.rate} {self.quote_currency_id} @ {self.as_of:%Y-%m-%d}"
