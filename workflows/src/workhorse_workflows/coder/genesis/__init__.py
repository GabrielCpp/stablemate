"""`genesis` — turn a directory into something the author and coder can both stand on.

Nothing hands off to this flow. It produces the preconditions the main loop *assumes* — a
git repo with a commit, an `agents.yml` carrying a `workspace:` block, farrier's packs and
scaffolds installed, and a service skeleton with its marker file — so it is entered
directly, as `workhorse run coder genesis`.

The flow and the nodes only it calls are one directory: `flow.py` is the machine and
`nodes.py` is its own non-agent work. What it does *not* keep private is the assertion
itself: genesis's postcondition is the main loop's precondition, and both read
`shared/contract.py` so they cannot drift apart silently.
"""
from __future__ import annotations

from workhorse_workflows.coder.genesis.flow import Genesis

__all__ = ["Genesis"]
