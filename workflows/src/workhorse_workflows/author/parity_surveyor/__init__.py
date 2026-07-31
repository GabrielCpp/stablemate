"""`parity-surveyor` — the second survey sub-graph `author` reaches with `self.handoff(...)`.

A parity survey walks a baseline inventory rather than discovering one: the units are
given, and each unit's record answers "does the replacement hold what the baseline held".
The flow and the nodes only it calls are one directory — `flow.py` and `nodes/` — and the
middle it shares with `surveyor` is in [`shared/survey/`](../shared/survey).

The handoff boundary is the one [`surveyor`](../surveyor) documents: `handoff` returns the
sub-flow's `Done(...)` **value**, `self.output(node)` cannot see across it, prompt paths
still resolve against `author/prompts/`, and the sub-flow drives on its own transition
budget.
"""
from __future__ import annotations

from workhorse_workflows.author.parity_surveyor.flow import ParitySurveyor

__all__ = ["ParitySurveyor"]
