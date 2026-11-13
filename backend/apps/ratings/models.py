from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.core.models import TimeStampedModel


class Rating(TimeStampedModel):
    port_call = models.ForeignKey("portcalls.PortCall", on_delete=models.PROTECT, related_name="ratings")
    rater_organization = models.ForeignKey("accounts.Organization", on_delete=models.PROTECT, related_name="ratings_given")
    rater_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    ratee_organization = models.ForeignKey("accounts.Organization", on_delete=models.PROTECT, related_name="ratings_received")
    vendor_request = models.ForeignKey("requests.Request", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    score = models.SmallIntegerField()
    comment = models.TextField(default="", blank=True)

    class Meta:
        db_table = "ratings"
        indexes = [models.Index(fields=["ratee_organization"], name="rating_ratee_idx")]
        constraints = [
            models.UniqueConstraint(fields=["port_call", "rater_organization", "ratee_organization"], name="rating_once_uniq"),
            models.CheckConstraint(condition=Q(score__gte=1, score__lte=5), name="rating_score_chk"),
            models.CheckConstraint(condition=~Q(rater_organization=F("ratee_organization")), name="rating_no_self_chk"),
        ]
