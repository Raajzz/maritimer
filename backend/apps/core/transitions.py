"""Tiny state-machine helper. Each domain app declares its table in `<app>/transitions.py`
mirroring STATE_MACHINES.md; tests assert the tables equal the document."""
from dataclasses import dataclass

from .exceptions import InvalidTransition


@dataclass(frozen=True)
class Transition:
    sources: frozenset
    target: str


class StateMachine:
    def __init__(self, name: str, table: dict[str, tuple[set, str]]):
        self.name = name
        self.table = {event: Transition(frozenset(str(s) for s in src), str(dst)) for event, (src, dst) in table.items()}

    def can(self, event: str, current: str) -> bool:
        transition = self.table.get(event)
        return bool(transition and str(current) in transition.sources)

    def assert_can(self, event: str, current: str) -> str:
        transition = self.table.get(event)
        if transition is None:
            raise InvalidTransition(f"Unknown {self.name} event '{event}'.")
        if str(current) not in transition.sources:
            raise InvalidTransition(
                f"Cannot {event.replace('_', ' ')} a {self.name} in status {current}.",
                details={"event": event, "current": str(current), "allowed_from": sorted(transition.sources)},
            )
        return transition.target

    def as_edges(self) -> set[tuple[str, str, str]]:
        return {(src, event, t.target) for event, t in self.table.items() for src in t.sources}
