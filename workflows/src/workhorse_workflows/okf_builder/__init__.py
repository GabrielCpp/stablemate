"""The `okf-builder` workflow: document a service until its book is clean and complete.

Ported from `base-library/workflows/okf-builder/`. The package has the layout
`workflows/README.md` prescribes for every workflow — one directory per *machine*:

* `workflow.py` — the composition root, and nothing else: the registry, the flow table,
  the dry-run stubs, the console script
* `main/` — the build machine a bare `run` starts, laid out like the walk beside it:
  `flow.py`, the `nodes/` it sequences, and the `prompts/` it renders
* `walkthrough_web/` — the sub-graph `self.handoff(...)` reaches: `flow.py` beside the
  `nodes/` and `prompts/` only it calls
* `shared/` — what a second machine also reaches: the `blueprint`, `paths`, `schemas`,
  `stubs`, and the two nodes both drains run (`worklist`, `checkpoint`)

Every agent turn's Markdown lives in the `prompts/` of the flow that renders it, and
paths are written from this package root down (`main/prompts/investigate.md`), because
that root is what `workflow.py` declares as the registry's `package`.

`shared/schemas.py` is a single module rather than `author`'s package: eighteen models is
what `research` carries, and splitting them would put the sub-flow's four in a file of
their own for no reader's benefit.
"""
from __future__ import annotations
