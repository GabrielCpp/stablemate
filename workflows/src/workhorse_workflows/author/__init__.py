"""The `author` workflow: turn a backlog into epics and stories the coder can build.

Ported from `base-library/workflows/author/`. The package has the layout
`workflows/README.md` prescribes for every workflow — one directory per *machine*:

* `workflow.py` — the main machine, and nothing else
* `nodes/` — the non-agent work only that machine calls, grouped by subject
* `surveyor/`, `parity_surveyor/` — the sub-graphs `self.handoff(...)` reaches: each
  `flow.py` beside the `nodes/` only it calls
* `story_edit/`, `epic_edit/` — story-intent and epic-reconciliation edit flows
* `shared/` — what a second machine also reaches: `paths`, `schemas`, and the `survey`
  library both survey flows walk
* `prompts/` — every agent turn's Markdown, at the package root because a sub-flow's
  prompt path resolves against the *parent* package directory
"""
from __future__ import annotations
