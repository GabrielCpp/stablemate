"""D1's dispatch table (§4.1): which node type a runner can be given a row for."""
from __future__ import annotations

DISPATCH_TABLE: dict[str, dict[str, str] | str] = {
    "interaction": {"web": "playwright", "mobile": "maestro"},
    "endpoint": {"web": "http", "mobile": "http", "http": "http"},
    "command": "cli",
}
OBSERVED_TYPES = frozenset({"flow", "component", "screen", "field", "invocation", "method"})
OBSERVE_ROW: dict[str, str] = {
    "web": "playwright", "mobile": "maestro", "http": "http", "cli": "cli",
}
BUILT_TARGETS = frozenset({"playwright", "http", "cli", "maestro"})
CONCEPTUAL_TYPES = frozenset({"concept"})


def hosts_observation(node_type: str) -> bool:
    """Whether the table can name a row for *node_type* under some driver.

    A `concept` node is a definition, so no runner ever stands where it does and no
    check declared on it could be performed. An obligation minted on one can carry
    context, never live evidence.
    """
    return node_type in OBSERVED_TYPES or node_type in DISPATCH_TABLE


def owes_live_evidence(node_type: str) -> bool:
    """Whether a check declared on *node_type* could ever be performed against a system.

    A `concept` page is a piece of thinking about the user and the system, so there is
    nothing there to measure and no live evidence it could owe. A type this does not
    recognise still owes it: an unclassified node is a missing fact, not a definition.
    """
    return node_type not in CONCEPTUAL_TYPES


__all__ = [
    "BUILT_TARGETS", "CONCEPTUAL_TYPES", "DISPATCH_TABLE", "OBSERVED_TYPES", "OBSERVE_ROW",
    "hosts_observation", "owes_live_evidence",
]
