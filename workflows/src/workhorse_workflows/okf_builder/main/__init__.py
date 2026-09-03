"""`main` — the build machine a bare `workhorse-okf-builder run` starts.

Laid out like the walk beside it: `flow.py` is the machine, `nodes/` is the non-agent
work only it sequences (`prepare`, `inventory_source`, `compute_coverage`),
and `prompts/` holds the four envelopes it renders — including the whole `repair/`
fragment directory `repair.md` dispatches into. What the walk *also* calls is in
[`shared/`](../shared).

It is a directory rather than a `workflow.py` at the package root so the two graphs sit
side by side and the root holds only the composition root. Its prompt paths are written
from that root down (`main/prompts/investigate.md`), which is what
[`../workflow.py`](../workflow.py) declares as the registry's `package`.
"""
from __future__ import annotations

from workhorse_workflows.okf_builder.main.flow import (
    MAX_RESCAN_ROUNDS,
    MAX_STALL_ROUNDS,
    OkfBuilder,
)

__all__ = ["MAX_RESCAN_ROUNDS", "MAX_STALL_ROUNDS", "OkfBuilder"]
