from __future__ import annotations
from typing import Any

from workhorse.graph.nodes import BranchNode
from workhorse.graph.context import WorkflowContext

_OPS = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "<":  lambda a, b: _coerce(a) < _coerce(b),
    ">":  lambda a, b: _coerce(a) > _coerce(b),
    "<=": lambda a, b: _coerce(a) <= _coerce(b),
    ">=": lambda a, b: _coerce(a) >= _coerce(b),
}

_UNRESOLVED = object()


def evaluate(node: BranchNode, context: WorkflowContext) -> tuple[str, Any]:
    """
    Resolve the branch condition against the context.

    Returns (next_node_id, resolved_value).

    Guardrail: if the branch path can't be resolved — the producing step returned
    an unexpected shape, a null, or nothing (a common LLM failure mode) — we route
    to the node's ``default`` rather than crashing the whole run. A branch with no
    ``default`` still raises, but with an actionable message.
    """
    value = context.get_dotpath(node.path, default=_UNRESOLVED)
    if value is _UNRESOLVED:
        if node.default:
            print(
                f"[{node.id}] ⚠ branch path '{node.path}' is missing or not "
                f"traversable in the context (the producing step likely returned an "
                f"unexpected shape) — routing to default '{node.default}'",
                flush=True,
            )
            return node.default, None
        raise RuntimeError(
            f"Branch node '{node.id}': path '{node.path}' could not be resolved in "
            f"the context (the producing step returned an unexpected shape or no "
            f"value) and no 'default' is set to fall back to. Add a 'default' to "
            f"this branch to make it resilient to malformed upstream output."
        )

    str_value = str(value)

    # Equality map first (most common pattern for enum-style branching)
    if str_value in node.cases:
        return node.cases[str_value], value

    # Ordered conditions (numeric / string comparisons)
    for cond in node.conditions:
        op_fn = _OPS.get(cond.op)
        if op_fn is None:
            raise ValueError(f"Unknown branch operator '{cond.op}' in node '{node.id}'")
        if op_fn(str_value, cond.value):
            return cond.next, value

    if node.default:
        return node.default, value

    raise RuntimeError(
        f"Branch node '{node.id}': no case matched value '{value}' "
        f"for path '{node.path}' and no default is set"
    )


def _coerce(v: Any) -> float | str:
    try:
        return float(v)
    except (TypeError, ValueError):
        return str(v)
