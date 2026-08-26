"""The diff-to-OKF context packet's two gate results, shared by `docs` and `qa`.

`build-qa-okf-context.py` and `validate-qa-okf-context.py` are one script pair called from
two flows under two different output keys — `documentation_context_build` /
`documentation_context_result` in `docs`, `qa_context_build` / `qa_context_result` in `qa`.
The keys were the YAML's way of keeping two calls of the same script apart in one run
context; the driver keys a node's output by node name inside the *flow's own* subscope, so
the two flows cannot collide and the `output_key` argument has no job left. One model
serves both.
"""
from __future__ import annotations

from typing import Any, Literal

from workhorse_workflows.coder.shared.schemas._base import CoderResult


class OkfContextResult(CoderResult):
    """`ostler qa context` / `ostler qa context-validate` — the packet, and whether it holds.

    `status` is `passed` or `invalid` and nothing else: both scripts computed it themselves
    from a returncode rather than reading it off ostler, so there is no third arm and no
    blank to route. `ostler` is the raw payload, kept because `notes` is only ever a
    summary of it and the packet itself is what the next gate reads off disk.
    """

    status: Literal["passed", "invalid"] = "invalid"
    notes: str = ""
    ostler: dict[str, Any] = {}


__all__ = ["OkfContextResult"]
