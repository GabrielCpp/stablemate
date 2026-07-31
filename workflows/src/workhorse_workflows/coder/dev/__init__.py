"""`dev` — plan a story and implement it, one service layer at a time.

The sub-graph the main loop reaches with `self.handoff(Dev, ...)`, and a registered flow
in its own right (`workhorse run coder dev`). `flow.py` is the machine; it calls no nodes
of its own, because every subject it touches — the planning gates, the per-layer
implementation loop, the story spine — is one a second graph also touches, so all of it is
in [`shared/`](../shared) (`shared/dev.py`, `shared/story.py`).

The handoff boundary is the one [the package docstring](../__init__.py) describes:
`handoff` returns the sub-flow's `Done(...)` **value**, `self.output(node)` cannot see
across it, prompt paths still resolve against `coder/prompts/`, and the sub-flow drives on
its own transition budget.
"""
from __future__ import annotations

from workhorse_workflows.coder.dev.flow import Dev

__all__ = ["Dev"]
