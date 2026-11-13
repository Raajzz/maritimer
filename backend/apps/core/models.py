from django.conf import settings
from django.db import models

from .enums import Role, check_in


class CITextField(models.TextField):
    """Case-insensitive text (Postgres citext). Requires the citext extension (core migration 0001)."""

    def db_type(self, connection):
        return "citext"


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditLog(models.Model):
    """Append-only (SCHEMA.md §2.13). Written only by apps.core.audit.audit()."""

    actor_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    actor_role = models.CharField(max_length=16, null=True, blank=True)
    actor_organization = models.ForeignKey("accounts.Organization", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    action = models.CharField(max_length=64)
    entity_type = models.CharField(max_length=48)
    entity_id = models.BigIntegerField()
    port_call = models.ForeignKey("portcalls.PortCall", null=True, blank=True, on_delete=models.PROTECT, related_name="audit_entries")
    from_state = models.CharField(max_length=32, null=True, blank=True)
    to_state = models.CharField(max_length=32, null=True, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_log"
        indexes = [
            models.Index(fields=["entity_type", "entity_id", "created_at"], name="audit_entity_idx"),
            models.Index(fields=["port_call", "created_at"], name="audit_port_call_idx"),
            models.Index(fields=["actor_user", "created_at"], name="audit_actor_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(actor_role__isnull=True) | check_in("actor_role", Role), name="audit_actor_role_chk"),
        ]
        ordering = ["-created_at", "-id"]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise RuntimeError("audit_log is append-only")
        super().save(*args, **kwargs)
