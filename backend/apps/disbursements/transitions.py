"""STATE_MACHINES.md §4 — PDA and FDA."""
from apps.core.enums import AccountStatus as A
from apps.core.transitions import StateMachine

PDA_MACHINE = StateMachine(
    "PDA",
    {
        "issue": ({A.DRAFT}, A.ISSUED),
        "approve": ({A.ISSUED}, A.APPROVED),
        "reject": ({A.ISSUED}, A.REJECTED),
        "revise": ({A.ISSUED, A.REJECTED}, A.SUPERSEDED),
        "void": ({A.DRAFT, A.ISSUED, A.APPROVED}, A.VOID),
    },
)

FDA_MACHINE = StateMachine(
    "FDA",
    {
        "issue": ({A.DRAFT}, A.ISSUED),
        "revise": ({A.ISSUED}, A.SUPERSEDED),
        "finalize": ({A.ISSUED}, A.FINAL),
        "discard": ({A.DRAFT}, A.VOID),
        # Clarification recorded in PROGRESS.md (C1): discarding a revision draft restores the
        # previous version, which was SUPERSEDED by the revise, back to ISSUED.
        "restore": ({A.SUPERSEDED}, A.ISSUED),
    },
)
