"""Permission layers (API.md §0): IsAuthenticated → IsApproved → role gate → object scoping (selectors)."""
from rest_framework.permissions import BasePermission

from .enums import Role, UserStatus, VerificationStatus
from .exceptions import NotApproved


def next_step(user) -> str:
    if user.status == UserStatus.NEW:
        return "CHOOSE_ROLE"
    if user.status == UserStatus.ONBOARDING:
        return "ONBOARDING"
    if user.status == UserStatus.PENDING_REVIEW:
        return "PENDING_REVIEW"
    if user.status == UserStatus.REJECTED:
        return "REJECTED"
    if user.status == UserStatus.SUSPENDED:
        return "SUSPENDED"
    if user.role != Role.ADMIN:
        org = user.organization
        if org is None:
            return "ONBOARDING"
        if org.verification_status == VerificationStatus.SUSPENDED:
            return "SUSPENDED"
        if org.verification_status == VerificationStatus.REJECTED:
            return "REJECTED"
        if org.verification_status != VerificationStatus.APPROVED:
            return "PENDING_REVIEW"
    return "APP"


def is_fully_approved(user) -> bool:
    return bool(user and user.is_authenticated and next_step(user) == "APP")


class IsApproved(BasePermission):
    """User APPROVED and (ADMIN or organization APPROVED). Enforced on every endpoint except auth/onboarding."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        step = next_step(user)
        if step != "APP":
            raise NotApproved(user.status, step)
        return True


class _RolePermission(BasePermission):
    roles: tuple = ()
    message = "Your role cannot perform this action."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role in self.roles)


def roles(*allowed):
    names = tuple(str(r) for r in allowed)
    return type(f"RolePermission_{'_'.join(names)}", (_RolePermission,), {"roles": names})


IsAdminRole = roles(Role.ADMIN)
IsOwner = roles(Role.OWNER)
IsAgent = roles(Role.AGENT)
IsMerchant = roles(Role.MERCHANT)


def approved(*allowed):
    """Permission list for approved users, optionally restricted to roles. Keeps IsApproved on every endpoint."""
    from rest_framework.permissions import IsAuthenticated

    classes = [IsAuthenticated, IsApproved]
    if allowed:
        classes.append(roles(*allowed))
    return classes
