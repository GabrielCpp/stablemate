"""`review` — review a story's implementation and drive the findings to settled.

The sub-graph the main loop reaches with `self.handoff(Review, ...)` and reads nothing
back from, and a registered flow in its own right (`workhorse run coder review`) for a PR
that no story pipeline produced. `flow.py` is the machine; where a review runs, what its
findings settled to and what a human dropped in are in `shared/review.py`, because the QA
graph resolves the same context when it triages.

The handoff boundary is the one [the package docstring](../__init__.py) describes:
`handoff` returns the sub-flow's `Done(...)` **value**, `self.output(node)` cannot see
across it, prompt paths still resolve against `coder/prompts/`, and the sub-flow drives on
its own transition budget.
"""
from __future__ import annotations

from workhorse_workflows.coder.review.flow import Review

__all__ = ["Review"]
