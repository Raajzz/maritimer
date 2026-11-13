"""STATE_MACHINES.md §3 — port call."""
from apps.core.enums import PortCallStatus as P
from apps.core.transitions import StateMachine

PORT_CALL_MACHINE = StateMachine(
    "port call",
    {
        "pda_issue": ({P.PDA_PENDING}, P.PDA_SENT),
        "pda_approve": ({P.PDA_SENT}, P.PDA_APPROVED),
        "pda_reject": ({P.PDA_SENT}, P.PDA_PENDING),
        "pda_revise": ({P.PDA_SENT, P.PDA_PENDING}, P.PDA_PENDING),
        "advance_received": ({P.PDA_APPROVED}, P.ADVANCE_RECEIVED),
        "arrive": ({P.PDA_APPROVED, P.ADVANCE_RECEIVED}, P.IN_PORT),
        "depart": ({P.IN_PORT}, P.DEPARTED),
        "fda_issue": ({P.DEPARTED, P.FDA_ISSUED, P.DISPUTED}, P.FDA_ISSUED),
        "dispute_open": ({P.FDA_ISSUED, P.DISPUTED}, P.DISPUTED),
        "disputes_cleared": ({P.DISPUTED}, P.FDA_ISSUED),
        "fda_finalize": ({P.FDA_ISSUED}, P.FDA_FINAL),
        "settle": ({P.FDA_FINAL}, P.SETTLED),
        "close": ({P.SETTLED}, P.CLOSED),
        "cancel": ({P.PDA_PENDING, P.PDA_SENT, P.PDA_APPROVED, P.ADVANCE_RECEIVED}, P.CANCELLED),
    },
)

# Owners may cancel only before PDA approval (STATE_MACHINES.md §3 cancel row).
OWNER_CANCELLABLE = {P.PDA_PENDING, P.PDA_SENT}
# Agent may edit eta/etd/berth/notes outside these states.
AGENT_EDIT_BLOCKED = {P.FDA_FINAL, P.SETTLED, P.CLOSED, P.CANCELLED}
