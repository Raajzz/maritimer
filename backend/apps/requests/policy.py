"""Request directionality policy (SCHEMA.md D5). Opening a direction = enabling a row."""
from apps.core.exceptions import PolicyDenied

from .models import RequestRolePolicy


def get_policy(request_type, from_role, to_role):
    return RequestRolePolicy.objects.filter(request_type=request_type, from_role=from_role, to_role=to_role, is_enabled=True).first()


def assert_allowed(request_type, from_role, to_role):
    policy = get_policy(request_type, from_role, to_role)
    if policy is None:
        raise PolicyDenied(
            f"{from_role} cannot send {request_type} requests to {to_role}.",
            {"request_type": request_type, "from_role": from_role, "to_role": to_role},
        )
    return policy


def allowed_targets(request_type, from_role):
    return list(
        RequestRolePolicy.objects.filter(request_type=request_type, from_role=from_role, is_enabled=True).values_list("to_role", flat=True)
    )
