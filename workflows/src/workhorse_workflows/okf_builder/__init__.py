"""The `okf-builder` workflow: document a service until its book is clean and complete.

Ported from `base-library/workflows/okf-builder/`. The package has the layout
`workflows/README.md` prescribes for every workflow — one directory per *machine*:

* `workflow.py` — the main machine, and nothing else
* `nodes/` — the non-agent work only that machine calls, grouped by subject
* `walkthrough_web/` — the sub-graph `self.handoff(...)` reaches: `flow.py` beside the
  `nodes/` only it calls
* `shared/` — what a second machine also reaches: the `blueprint`, `paths`, `schemas`,
  `stubs`, and the two nodes both drains run (`worklist`, `checkpoint`)
* `prompts/` — every agent turn's Markdown, at the package root because a sub-flow's
  prompt path resolves against the *parent* package directory

`shared/schemas.py` is a single module rather than `author`'s package: eighteen models is
what `research` carries, and splitting them would put the sub-flow's four in a file of
their own for no reader's benefit.
"""
from __future__ import annotations
