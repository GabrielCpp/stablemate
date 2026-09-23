"""D1's dispatch table (§4.1): which node type a runner can be given a row for."""
from __future__ import annotations

from ostler.qa.plan_source import ScenarioRefusal

DISPATCH_TABLE: dict[str, dict[str, str] | str] = {
    "interaction": {"web": "playwright", "mobile": "maestro"},
    "endpoint": {"web": "http", "mobile": "http", "http": "http"},
    "command": "cli",
}
OBSERVED_TYPES = frozenset({"flow", "component", "screen", "field", "invocation"})
OBSERVE_ROW: dict[str, str] = {
    "web": "playwright", "mobile": "maestro", "http": "http", "cli": "cli",
}
BUILT_TARGETS = frozenset({"playwright", "http", "cli", "maestro"})
NO_LIVE_EVIDENCE_TYPES = frozenset({"concept", "method"})


def hosts_observation(node_type: str) -> bool:
    """Whether the table can name a row for *node_type* under some driver.

    A `concept` node is a definition and a `method` is a callable inside the source, so
    no runner ever stands where either does and no check declared on one could be
    performed. An obligation minted on one can carry context, never live evidence.
    """
    return node_type in OBSERVED_TYPES or node_type in DISPATCH_TABLE


def owes_live_evidence(node_type: str) -> bool:
    """Whether a check declared on *node_type* could ever be performed against a system.

    A `concept` page is a piece of thinking about the user and the system, and a `method`
    is implementation the user never touches. Each explains the surface a user drives, so
    neither owes live evidence of its own: the command, endpoint or interaction that
    reaches it does. A type this does not recognise still owes it: an unclassified node is
    a missing fact, not a definition.
    """
    return node_type not in NO_LIVE_EVIDENCE_TYPES


def dispatch_target(node_type: str, driver: str | None) -> str | ScenarioRefusal:
    """The built target D1's table — or `OBSERVE_ROW`, for a type nobody performs — names, or why none."""
    row = OBSERVE_ROW if node_type in OBSERVED_TYPES else DISPATCH_TABLE.get(node_type)
    if row is None:
        if node_type == "concept":
            return ScenarioRefusal("uncompilable-claim", (
                "the book links this step to a 'concept' node — a definition, not a place a "
                "claim can be observed, so D1's dispatch table (§4.1) owes it no row"
            ))
        if node_type == "method":
            return ScenarioRefusal("uncompilable-claim", (
                "the book links this step to a 'method' node, which is source a user never "
                "drives. Link the step to the command, endpoint or interaction that reaches it"
            ))
        return ScenarioRefusal("uncompilable-claim", (
            f"the book links this step to a {node_type or 'untyped'!r} node, which D1's "
            "dispatch table (§4.1) names no row for"
        ))
    if isinstance(row, str):
        target = row
    else:
        if driver is None:
            return ScenarioRefusal("uncompilable-claim", (
                "the surface this step's node lives on states no `driver:` on any `runbook`, so "
                "D1's dispatch table (§4.1) cannot determine what performs this step"
            ))
        target = row.get(driver)
        if target is None:
            return ScenarioRefusal("uncompilable-claim", (
                f"D1's dispatch table (§4.1) names no target for a {node_type} step on a "
                f"{driver!r}-driven surface"
            ))
    if target not in BUILT_TARGETS:
        where = "for every driver" if isinstance(row, str) else f"on a {driver!r}-driven surface"
        return ScenarioRefusal("needs-target-backend", (
            f"D1's dispatch table (§4.1) names {target!r} for a {node_type} step {where}, "
            f"but this compiler builds no {target} path yet"
        ))
    return target


__all__ = [
    "BUILT_TARGETS", "DISPATCH_TABLE", "NO_LIVE_EVIDENCE_TYPES", "OBSERVED_TYPES", "OBSERVE_ROW",
    "dispatch_target", "hosts_observation", "owes_live_evidence",
]
