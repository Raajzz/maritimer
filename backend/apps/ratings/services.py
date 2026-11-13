from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Avg, Count

from apps.accounts.models import AgentProfile, MerchantProfile
from apps.core.audit import audit
from apps.core.enums import OrgType, PortCallStatus, Role
from apps.core.exceptions import Conflict, Forbidden, InvalidTransition
from apps.core.services import require
from apps.portcalls.services import lock_port_call

from .models import Rating

RATEABLE_STATES = {PortCallStatus.SETTLED, PortCallStatus.CLOSED}


def _refresh_aggregate(org):
    stats = Rating.objects.filter(ratee_organization=org).aggregate(avg=Avg("score"), count=Count("id"))
    avg = Decimal(str(stats["avg"] or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    model = AgentProfile if org.type == OrgType.AGENT else MerchantProfile if org.type == OrgType.MERCHANT else None
    if model is not None:
        model.objects.filter(organization=org).update(rating_avg=avg, rating_count=stats["count"])


@transaction.atomic
def rate(*, actor, port_call, ratee_organization_id, score, comment="", vendor_request_id=None):
    port_call = lock_port_call(port_call)
    # v1 policy: owners rate the agent of the call. Agent→merchant is reserved (SCHEMA.md D2/§2.12).
    if actor.role != Role.OWNER or actor.organization_id != port_call.owner_organization_id:
        raise Forbidden("Only the owner of this port call can rate in v1.")
    require(int(ratee_organization_id) == port_call.agent_organization_id, "Owners rate the port call's agent.",
            {"ratee_organization_id": ["Must be the agent of this port call."]})
    if port_call.status not in RATEABLE_STATES:
        raise InvalidTransition("Ratings open once the port call is settled.")
    score = int(score)
    require(1 <= score <= 5, "Score must be 1–5.", {"score": ["1 to 5."]})
    if Rating.objects.filter(port_call=port_call, rater_organization_id=actor.organization_id, ratee_organization_id=ratee_organization_id).exists():
        raise Conflict("You have already rated this port call.")
    rating = Rating.objects.create(
        port_call=port_call,
        rater_organization_id=actor.organization_id,
        rater_user=actor,
        ratee_organization_id=ratee_organization_id,
        vendor_request_id=vendor_request_id,
        score=score,
        comment=comment or "",
    )
    _refresh_aggregate(port_call.agent_organization)
    audit(actor=actor, action="rating.created", entity=rating, port_call=port_call, metadata={"score": score})
    return rating
