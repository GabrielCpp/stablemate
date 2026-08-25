"""`main` — the backlog→epics→stories machine a bare `workhorse-author run` starts.

Laid out exactly as the sub-flows beside it: `flow.py` is the state machine and
[`nodes/`](nodes) holds the deterministic work it sequences — config, epic selection,
story files, coverage, the git tail. Those nodes are also imported by `epic-edit` and
`story-edit`, which are the two flows that edit the same artifacts this machine writes;
what is genuinely common to *every* flow, survey included, lives in
[`../shared/`](../shared) instead.

`main` is not registered in `add_flows` — it is the entry point, which is how it was
always reached, and naming it twice would give one machine two names. The registry that
composes the distribution stays at [`../workflow.py`](../workflow.py), because the package
root is what every flow's prompt paths and the repo's `.agents/flavors/author/` resolve
against.
"""
from __future__ import annotations

from workhorse_workflows.author.main.flow import Author

__all__ = ["Author"]
