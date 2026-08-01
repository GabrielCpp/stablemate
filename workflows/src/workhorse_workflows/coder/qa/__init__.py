"""`qa` — plan QA for a story, run it, and refuse to believe it passed.

The sub-graph the main loop reaches with `self.handoff(Qa, ...)`, and a registered flow in
its own right (`workhorse-coder run qa`). It is the densest graph in the four workflows,
and it is the only sub-flow whose own nodes need a package rather than a module:

* `nodes/qa` — clear the evidence, bring the stack up, validate the plan, run it
* `nodes/evidence` — the gate that fails closed: is the claimed pass backed by proof
* `nodes/regression` — which committed journey suites this story touched, and how they ran
* `nodes/hygiene` — the two pre-commit gates: stray screenshots, and sentinel IDs

The subjects it shares with other graphs are not here: the story spine, the review nodes,
the OKF obligation packet and the documentation check are in [`shared/`](../shared).

The handoff boundary is the one [the package docstring](../__init__.py) describes:
`handoff` returns the sub-flow's `Done(...)` **value**, `self.output(node)` cannot see
across it, prompt paths still resolve against `coder/prompts/`, and the sub-flow drives on
its own transition budget.
"""
from __future__ import annotations

from workhorse_workflows.coder.qa.flow import Qa

__all__ = ["Qa"]
