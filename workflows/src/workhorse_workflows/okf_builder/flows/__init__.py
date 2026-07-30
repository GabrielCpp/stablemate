"""The sub-graph `okf-builder` reaches with `self.handoff(...)`.

One flow, `walkthrough-web`, which the YAML kept under a `flows:` mapping at the bottom of
`okf-builder/workflow.yaml`. It is here for the same reason author's two are: a state
machine is a class, and a second machine indented inside the first is a second machine
either way.

Everything `author/flows/__init__.py` says about the boundary holds here too — `handoff`
returns the sub-flow's `Done(...)` **value**, only the run *writer* is subscoped (so the
walk's prompt path resolves against `okf_builder/prompts/` like every other one),
`self.output(node)` cannot see across, and the sub-flow drives on its own transition
budget. What is specific to this one is that it is **standalone-invokable**, and was
designed that way in the YAML::

    workhorse run okf-builder walkthrough-web --params '{"service":"acme"}'

which is why its `setup()` re-derives every path from `docs_path` rather than taking them
from the parent's `ctx`: a walk must be runnable against a book an earlier run built.
"""
from __future__ import annotations

from workhorse_workflows.okf_builder.flows.walkthrough_web import WalkthroughWeb

__all__ = ["WalkthroughWeb"]
