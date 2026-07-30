"""The sub-graphs `author` reaches with `self.handoff(...)`.

The YAML kept these under a `flows:` mapping inside `author/workflow.yaml`, which is why
that file is 2,116 lines: three state machines in one document, distinguishable only by
indentation. Here each is a `Workflow` subclass in its own module, and the main graph
names it at the callsite::

    result = self.handoff(ParitySurveyor, baseline_inventory=self.baseline_inventory, …)

`handoff` returns the sub-flow's `Done(...)` **value**, not the instance, so what a
sub-flow hands back is whatever its terminal state returned — a typed model the caller
reads fields off. Two things follow from `Engine.handoff` that a sub-flow author has to
know, because neither is obvious from the callsite:

* only the run **writer** is subscoped, not the environment. A sub-flow's prompt paths
  therefore resolve against the *parent* package directory, which is why the prompts a
  flow here reaches live under `author/prompts/` like every other one;
* `self.output(node)` reads that subscope, so it cannot see a node the parent ran and
  the parent cannot see one a sub-flow ran. A value that has to cross the boundary
  crosses it as an argument or as the `Done` value.

Each sub-flow gets its own transition budget, because `handoff` drives it through a
fresh `drive()` — a per-unit loop here cannot exhaust the parent's.
"""
from __future__ import annotations

from workhorse_workflows.author.flows.parity_surveyor import ParitySurveyor
from workhorse_workflows.author.flows.surveyor import Surveyor

__all__ = ["ParitySurveyor", "Surveyor"]
