"""Every transition table in code must equal the diagram in STATE_MACHINES.md (self-loops ignored)."""
import re
from pathlib import Path

import pytest

from apps.accounts.transitions import USER_MACHINE
from apps.disbursements.transitions import FDA_MACHINE, PDA_MACHINE
from apps.disputes.transitions import DISPUTE_MACHINE
from apps.invoices.transitions import INVOICE_MACHINE
from apps.payments.transitions import PAYMENT_MACHINE, SETTLEMENT_MACHINE
from apps.portcalls.transitions import PORT_CALL_MACHINE
from apps.requests.transitions import REQUEST_MACHINE

DOC = Path(__file__).resolve().parents[2] / "STATE_MACHINES.md"
EDGE = re.compile(r"^\s*(\[\*\]|[A-Z_]+)\s*-->\s*([A-Z_]+)")

# Order of ```mermaid blocks in STATE_MACHINES.md
MACHINES = [
    ("user", USER_MACHINE),
    ("request", REQUEST_MACHINE),
    ("port call", PORT_CALL_MACHINE),
    ("PDA", PDA_MACHINE),
    ("FDA", FDA_MACHINE),
    ("vendor invoice", INVOICE_MACHINE),
    ("payment", PAYMENT_MACHINE),
    ("settlement", SETTLEMENT_MACHINE),
    ("dispute", DISPUTE_MACHINE),
]

# Edges implemented in code but not drawn in STATE_MACHINES.md. Each one is recorded in PROGRESS.md.
KNOWN_CLARIFICATIONS = {
    "FDA": {("SUPERSEDED", "ISSUED")},  # PROGRESS.md C1: discarding a revision draft restores the previous version
}


def doc_edges():
    text = DOC.read_text()
    blocks = re.findall(r"```mermaid\n(.*?)```", text, re.S)
    diagrams = [b for b in blocks if b.lstrip().startswith("stateDiagram")]
    result = []
    for block in diagrams:
        edges = set()
        for line in block.splitlines():
            m = EDGE.match(line)
            if m and m.group(1) != "[*]" and m.group(1) != m.group(2):
                edges.add((m.group(1), m.group(2)))
        result.append(edges)
    return result


def code_edges(machine):
    return {(src, dst) for src, _event, dst in machine.as_edges() if src != dst}


def test_doc_has_one_diagram_per_machine():
    assert len(doc_edges()) == len(MACHINES)


@pytest.mark.parametrize("index,name,machine", [(i, n, m) for i, (n, m) in enumerate(MACHINES)])
def test_transition_table_matches_document(index, name, machine):
    expected = doc_edges()[index] | KNOWN_CLARIFICATIONS.get(name, set())
    assert code_edges(machine) == expected, f"{name} machine differs from STATE_MACHINES.md"


def test_invalid_transition_raises():
    from apps.core.exceptions import InvalidTransition

    with pytest.raises(InvalidTransition):
        PORT_CALL_MACHINE.assert_can("fda_finalize", "DISPUTED")
    with pytest.raises(InvalidTransition):
        DISPUTE_MACHINE.assert_can("reopen", "RESOLVED")
    assert PORT_CALL_MACHINE.assert_can("arrive", "PDA_APPROVED") == "IN_PORT"
