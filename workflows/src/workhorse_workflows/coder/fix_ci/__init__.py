"""`fix_ci` — walk the workspace one repo at a time and get the epic branch's CI green.

The sub-graph the main loop's epic gate reaches with `self.handoff(FixCi, ...)`, and a
registered flow in its own right (`workhorse-coder run fix_ci`). `flow.py` is the machine;
the polling, fixing and pushing are in `shared/ci.py`, because the main graph runs the
same loop inline after it opens the epic's PR.

The handoff boundary is the one [the package docstring](../__init__.py) describes — and
this flow is why the per-sub-flow transition budget matters: a per-repo poll loop here
cannot exhaust the parent's.
"""
from __future__ import annotations

from workhorse_workflows.coder.fix_ci.flow import FixCi

__all__ = ["FixCi"]
