"""STATE_MACHINES.md §5 — vendor invoice."""
from apps.core.enums import InvoiceStatus as I
from apps.core.transitions import StateMachine

INVOICE_MACHINE = StateMachine(
    "vendor invoice",
    {
        "issue": ({I.DRAFT}, I.ISSUED),
        "accept": ({I.ISSUED}, I.ACCEPTED),
        "reject": ({I.ISSUED}, I.REJECTED),
        "reopen": ({I.REJECTED}, I.DRAFT),
        "mark_paid": ({I.ACCEPTED}, I.PAID),
        "void": ({I.DRAFT, I.ISSUED}, I.VOID),
    },
)
