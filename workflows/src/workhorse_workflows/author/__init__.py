"""The `author` workflow: turn a backlog into epics and stories the coder can build.

Ported from `base-library/workflows/author/`. The package is laid out the way the plan's
"One workflow, several files" section prescribes — `workflow.py` holds the machine and
nothing else, `nodes/` holds the non-agent work grouped by subject, `schemas/` holds the
models the seams need, `paths.py` holds the derivations, and `flows/` holds the
sub-graphs `self.handoff(...)` reaches.
"""
from __future__ import annotations
