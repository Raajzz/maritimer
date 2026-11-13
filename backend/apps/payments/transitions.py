"""STATE_MACHINES.md §6 (payment) and §7 (settlement)."""
from apps.core.enums import PaymentStatus as P
from apps.core.enums import SettlementStatus as S
from apps.core.transitions import StateMachine

PAYMENT_MACHINE = StateMachine(
    "payment",
    {
        "confirm": ({P.PENDING}, P.CONFIRMED),
        "cancel": ({P.PENDING}, P.CANCELLED),
    },
)

SETTLEMENT_MACHINE = StateMachine(
    "settlement",
    {
        "partial_payment": ({S.OPEN}, S.PARTIALLY_PAID),
        "paid_in_full": ({S.OPEN, S.PARTIALLY_PAID}, S.CLOSED),
        "force_close": ({S.OPEN, S.PARTIALLY_PAID}, S.CLOSED),
    },
)
