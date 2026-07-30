"""The `okf-builder` workflow: document a service until its book is clean and complete.

Ported from `base-library/workflows/okf-builder/`. The package follows the layout the
plan's "One workflow, several files" section prescribes and `author` established —
`workflow.py` holds the machine and nothing else, `nodes/` holds the non-agent work
grouped by subject, `schemas.py` holds the models the seams need, `paths.py` holds the
derivations, and `flows/` holds the sub-graph `self.handoff(...)` reaches.

`schemas.py` is a single module rather than `author`'s package: eighteen models is what
`research` carries, and splitting them would put the sub-flow's four in a file of their
own for no reader's benefit.
"""
from __future__ import annotations
