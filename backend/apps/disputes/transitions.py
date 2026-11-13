"""STATE_MACHINES.md §8 — dispute."""
from apps.core.enums import DisputeStatus as D
from apps.core.transitions import StateMachine

DISPUTE_MACHINE = StateMachine(
    "dispute",
    {
        "acknowledge": ({D.OPEN}, D.UNDER_REVIEW),
        "withdraw": ({D.OPEN, D.UNDER_REVIEW}, D.WITHDRAWN),
        "resolve": ({D.OPEN, D.UNDER_REVIEW}, D.RESOLVED),
        "reject": ({D.OPEN, D.UNDER_REVIEW}, D.REJECTED),
        "reopen": ({D.REJECTED}, D.OPEN),
    },
)
