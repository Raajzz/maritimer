from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.enums import DISPUTE_CLOSED, DISPUTE_LIVE, DisputeEventType, DisputeStatus, ResolutionType, check_in
from apps.core.models import TimeStampedModel


class Dispute(TimeStampedModel):
    reference = models.CharField(max_length=24, unique=True)
    port_call = models.ForeignKey("portcalls.PortCall", on_delete=models.PROTECT, related_name="disputes")
    line_item = models.ForeignKey("disbursements.DisbursementLineItem", on_delete=models.PROTECT, related_name="disputes")
    raised_by_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    raised_by_organization = models.ForeignKey("accounts.Organization", on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=16, choices=DisputeStatus.choices, default=DisputeStatus.OPEN)
    reason = models.TextField()
    disputed_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    resolution_type = models.CharField(max_length=16, choices=ResolutionType.choices, null=True, blank=True)
    resolution_note = models.TextField(default="", blank=True)
    resolved_by_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_in_account = models.ForeignKey(
        "disbursements.DisbursementAccount", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    adjustment_line_item = models.ForeignKey(
        "disbursements.DisbursementLineItem", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    reopen_count = models.SmallIntegerField(default=0)

    class Meta:
        db_table = "disputes"
        indexes = [models.Index(fields=["port_call", "status"], name="dispute_pc_status_idx")]
        constraints = [
            models.CheckConstraint(condition=check_in("status", DisputeStatus), name="dispute_status_chk"),
            models.CheckConstraint(
                condition=Q(resolution_type__isnull=True) | check_in("resolution_type", ResolutionType), name="dispute_resolution_type_chk"
            ),
            models.UniqueConstraint(fields=["line_item"], condition=Q(status__in=DISPUTE_LIVE), name="dispute_one_live_per_line_uniq"),
            models.CheckConstraint(
                condition=Q(status__in=DISPUTE_CLOSED, resolved_at__isnull=False)
                | (~Q(status__in=DISPUTE_CLOSED) & Q(resolved_at__isnull=True)),
                name="dispute_resolved_at_chk",
            ),
            models.CheckConstraint(
                condition=~Q(status=DisputeStatus.RESOLVED) | Q(resolution_type__in=[ResolutionType.ADJUSTED, ResolutionType.EXPLAINED]),
                name="dispute_resolved_type_chk",
            ),
            models.CheckConstraint(
                condition=~Q(resolution_type=ResolutionType.ADJUSTED) | Q(adjustment_line_item__isnull=False),
                name="dispute_adjusted_line_chk",
            ),
            models.CheckConstraint(condition=Q(reopen_count__gte=0, reopen_count__lte=1), name="dispute_reopen_once_chk"),
        ]


class DisputeEvent(models.Model):
    """Append-only dispute history."""

    dispute = models.ForeignKey(Dispute, on_delete=models.CASCADE, related_name="events")
    actor_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    event_type = models.CharField(max_length=24, choices=DisputeEventType.choices)
    from_status = models.CharField(max_length=16, null=True, blank=True)
    to_status = models.CharField(max_length=16, null=True, blank=True)
    body = models.TextField(default="", blank=True)
    file = models.ForeignKey("documents.StoredFile", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dispute_events"
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["dispute", "created_at"], name="dispute_event_idx")]
        constraints = [models.CheckConstraint(condition=check_in("event_type", DisputeEventType), name="dispute_event_type_chk")]
