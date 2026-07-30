"""The sub-graphs `coder` reaches with `self.handoff(...)`, and the two entered directly.

The YAML kept eight of these under a `flows:` mapping inside `coder/workflow.yaml`, which
is most of why that file is 4,366 lines: nine state machines in one document,
distinguishable only by indentation. Here each is a `Workflow` subclass in its own module,
and the caller names it at the callsite::

    result = self.handoff(FixCi, branch=epic, docs_path=self.docs_path)

Three of the flows in this package are never handed off to. `genesis`, `dream` and `fix`
live here because the YAML put them under `flows:`, but none is sequenced by the main loop:
`genesis` produces the preconditions the main loop *assumes*, `dream` runs after the work
like sleep, so that reflection never gates a story, and `fix` is a standalone drain of the
backlog the main loop also drains inline, on its own copy of the same nodes. All three are
entered directly, which under the driver means they are registered flows on the coder
`Registry` and reached as `workhorse run coder genesis`.

Two things follow from `Engine.handoff` that a sub-flow author has to know, because neither
is obvious from the callsite:

* only the run **writer** is subscoped, not the environment. A sub-flow's prompt paths
  therefore resolve against the *parent* package directory, which is why the prompts a
  flow here reaches live under `coder/prompts/` like every other one;
* `self.output(node)` reads that subscope, so it cannot see a node the parent ran and the
  parent cannot see one a sub-flow ran. A value that has to cross the boundary crosses it
  as an argument or as the `Done` value.

Each sub-flow gets its own transition budget, because `handoff` drives it through a fresh
`drive()` — a per-repo loop here cannot exhaust the parent's.
"""
from __future__ import annotations

from workhorse_workflows.coder.flows.dev import Dev
from workhorse_workflows.coder.flows.docs import Docs
from workhorse_workflows.coder.flows.dream import Dream
from workhorse_workflows.coder.flows.fix import Fix
from workhorse_workflows.coder.flows.fix_ci import FixCi
from workhorse_workflows.coder.flows.genesis import Genesis
from workhorse_workflows.coder.flows.qa import Qa
from workhorse_workflows.coder.flows.review import Review

__all__ = ["Dev", "Docs", "Dream", "Fix", "FixCi", "Genesis", "Qa", "Review"]
