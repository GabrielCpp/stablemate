"""`main` — the epic/story loop a bare `workhorse-coder run` starts.

The graph that sequences the eight sub-flows, laid out exactly as one of them: `flow.py`
is the machine and [`nodes/`](nodes) holds the nodes only this graph calls (opening,
merging and flagging a PR). It is *not* registered in `add_flows` — it is the entry point,
which is how it was always reached, and naming it twice would give one machine two names.

What is deliberately not here is the registry. [`../workflow.py`](../workflow.py) composes
the distribution — the blueprint, the flow table, the dry-run stubs, the console script —
and it stays at the package root because that root is what every flow's prompt paths and
the repo's `.agents/flavors/coder/` resolve against.
"""
from __future__ import annotations

from workhorse_workflows.coder.main.flow import Coder

__all__ = ["Coder"]
