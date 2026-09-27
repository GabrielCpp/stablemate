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
NO_LIVE_EVIDENCE_PAGES = frozenset({"concept", "format"})

OPS_TYPES = frozenset({"environment", "runbook", "step", "fixture"})
NO_ROW_REASON = (
    "the book links this step to a {node_type!r} node, which D1's dispatch table (§4.1) names no row for"
)
OPS_REASON = (
    "this claim sits on a {node_type!r} node, which runs no command a check can observe. "
    "A fact about where the stack runs belongs on a runbook step whose `run:` exits non-zero "
    "when the fact is false, so bringing the stack up checks it. A fact about what the product "
    "does belongs, with its `verify:`, on the invocation, endpoint or interaction that produces it"
)
NO_ROW_REASONS: dict[str, str] = {
    "concept": (
        "the book links this step to a 'concept' node — a definition, not a place a "
        "claim can be observed, so D1's dispatch table (§4.1) owes it no row"
    ),
    "method": (
        "the book links this step to a 'method' node, which is source a user never "
        "drives. Link the step to the command, endpoint or interaction that reaches it"
    ),
    **dict.fromkeys(OPS_TYPES, OPS_REASON),
}


def hosts_observation(node_type: str) -> bool:
    """Whether the table can name a row for *node_type* under some driver.

    A `concept` node is a definition and a `method` is a callable inside the source, so
    no runner ever stands where either does and no check declared on one could be
    performed. An obligation minted on one can carry context, never live evidence.
    """
    return node_type in OBSERVED_TYPES or node_type in DISPATCH_TABLE


def owes_live_evidence(node_type: str, page_type: str = "") -> bool:
    """Whether a check declared on *node_type*, on a *page_type* page, could ever be performed against a system.

    A `concept` page is a piece of thinking about the user and the system, and a `method`
    is implementation the user never touches. Each explains the surface a user drives, so
    neither owes live evidence of its own: the command, endpoint or interaction that
    reaches it does. The same holds for every node a `concept` or `format` page holds: a
    field of a definition or of a data shape is observed through the surface that reads
    or writes it, never where it is defined. A type this does not recognise still owes
    it: an unclassified node is a missing fact, not a definition.
    """
    return node_type not in NO_LIVE_EVIDENCE_TYPES and page_type not in NO_LIVE_EVIDENCE_PAGES


def dispatch_target(node_type: str, driver: str | None) -> str | ScenarioRefusal:
    """The built target D1's table — or `OBSERVE_ROW`, for a type nobody performs — names, or why none."""
    row = OBSERVE_ROW if node_type in OBSERVED_TYPES else DISPATCH_TABLE.get(node_type)
    if row is None:
        return ScenarioRefusal("uncompilable-claim", NO_ROW_REASONS.get(node_type, NO_ROW_REASON).format(
            node_type=node_type or "untyped",
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
    "BUILT_TARGETS", "DISPATCH_TABLE", "NO_LIVE_EVIDENCE_PAGES", "NO_LIVE_EVIDENCE_TYPES", "NO_ROW_REASONS", "OBSERVED_TYPES",
    "OBSERVE_ROW", "OPS_TYPES",
    "dispatch_target", "hosts_observation", "owes_live_evidence",
]
