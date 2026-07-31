"""`docs` — fold a finished story into the as-built OKF book, and refuse to believe it was.

The sub-graph the main loop reaches at four call sites with `self.handoff(Docs, ...)`, and
a registered flow in its own right (`workhorse run coder docs`). `flow.py` is the machine
and there is no `nodes.py` beside it: the QA graph also detects the book, builds the
obligation packet and verifies the story's documentation, so those nodes are in
[`shared/`](../shared) — `shared/docs.py` and `shared/okf.py`, named for the subject rather
than for this flow, because naming them after one of two callers is the mirroring this
layout exists to undo.

The handoff boundary is the one [the package docstring](../__init__.py) describes:
`handoff` returns the sub-flow's `Done(...)` **value**, `self.output(node)` cannot see
across it, prompt paths still resolve against `coder/prompts/`, and the sub-flow drives on
its own transition budget.
"""
from __future__ import annotations

from workhorse_workflows.coder.docs.flow import Docs

__all__ = ["Docs"]
