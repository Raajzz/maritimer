"""STATE_MACHINES.md §1 — user onboarding and organization verification."""
from apps.core.enums import UserStatus as U
from apps.core.enums import VerificationStatus as V
from apps.core.transitions import StateMachine

USER_MACHINE = StateMachine(
    "user",
    {
        "choose_role": ({U.NEW}, U.ONBOARDING),
        "submit_onboarding": ({U.ONBOARDING}, U.PENDING_REVIEW),
        "approve": ({U.PENDING_REVIEW}, U.APPROVED),
        "reject": ({U.PENDING_REVIEW}, U.REJECTED),
        "resubmit": ({U.REJECTED}, U.ONBOARDING),
        "suspend": ({U.APPROVED}, U.SUSPENDED),
        "reinstate": ({U.SUSPENDED}, U.APPROVED),
    },
)

ORGANIZATION_MACHINE = StateMachine(
    "organization",
    {
        "submit": ({V.DRAFT}, V.PENDING_REVIEW),
        "approve": ({V.PENDING_REVIEW}, V.APPROVED),
        "reject": ({V.PENDING_REVIEW}, V.REJECTED),
        "resubmit": ({V.REJECTED}, V.DRAFT),
        "suspend": ({V.APPROVED}, V.SUSPENDED),
        "reinstate": ({V.SUSPENDED}, V.APPROVED),
    },
)
