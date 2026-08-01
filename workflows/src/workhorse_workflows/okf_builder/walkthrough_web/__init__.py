"""`walkthrough-web` — the sub-graph `okf-builder` reaches with `self.handoff(...)`.

The flow and the nodes only it calls are one directory: `flow.py` is the machine,
`nodes/` is its own non-agent work (`walkthrough.py`, `stack.py`). Anything the build
*also* calls — `select_item`, `record`, `checkpoint_book`, the schemas, the blueprint —
is in [`shared/`](../shared) rather than duplicated here.

The handoff boundary is the usual one: `handoff` returns the sub-flow's `Done(...)`
**value**, `self.output(node)` cannot see across it, and the sub-flow drives on its own
transition budget. Only the run *writer* is subscoped, not the environment, so the walk's
prompt paths still resolve against `okf_builder/prompts/` like every other one.

What is specific to this flow is that it is **standalone-invokable**, and was designed
that way in the YAML::

    workhorse-okf-builder run walkthrough-web --params '{"service":"acme"}'

which is why its `setup()` re-derives every path from `docs_path` rather than taking them
from the parent's `ctx`: a walk must be runnable against a book an earlier run built.
"""
from __future__ import annotations

from workhorse_workflows.okf_builder.walkthrough_web.flow import WalkthroughWeb

__all__ = ["WalkthroughWeb"]
