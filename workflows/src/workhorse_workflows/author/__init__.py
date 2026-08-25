"""The `author` workflow: turn a backlog into epics and stories the coder can build.

Ported from `base-library/workflows/author/`. The package has the layout
`workflows/README.md` prescribes for every workflow — one directory per *machine*:

* `workflow.py` — the composition root, and nothing else: the registry, the flow table,
  the dry-run stubs, the console script
* `main/` — the backlog→epics→stories machine a bare `run` starts, laid out like any
  other flow: `flow.py`, the `nodes/` it sequences, and the `prompts/` it renders
* `surveyor/`, `parity_surveyor/` — the sub-graphs `self.handoff(...)` reaches: each
  `flow.py` beside the `nodes/` and `prompts/` only it calls
* `story_edit/`, `epic_edit/` — story-intent and epic-reconciliation edit flows
* `shared/` — what a second machine also reaches: `paths`, `schemas`, and the `survey`
  library both survey flows walk

Every agent turn's Markdown lives in the `prompts/` of the flow that renders it, and a
prompt two flows both render is **two files** — `write-story.md` exists under `main/` and
under `epic_edit/`, each free to diverge. Paths are written from this package root down
(`surveyor/prompts/assess-unit.md`), because that root is what `workflow.py` declares as
the registry's `package` and what every flow therefore renders against.
"""
from __future__ import annotations
