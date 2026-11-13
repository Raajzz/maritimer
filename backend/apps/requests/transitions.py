"""STATE_MACHINES.md §2 — generic request."""
from apps.core.enums import RequestStatus as R
from apps.core.transitions import StateMachine

REQUEST_MACHINE = StateMachine(
    "request",
    {
        "accept": ({R.PENDING}, R.ACCEPTED),
        "decline": ({R.PENDING}, R.DECLINED),
        "withdraw": ({R.PENDING}, R.WITHDRAWN),
        "expire": ({R.PENDING}, R.EXPIRED),
    },
)
