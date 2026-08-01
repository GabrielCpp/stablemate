"""`dream` — digest a finished run's process record into a durable ledger.

Nothing hands off to this flow. It is entered directly (`workhorse-coder run dream`) and
runs *after* the build work, like sleep, so that reflection never gates a story.

The flow and the nodes only it calls are one directory: `flow.py` is the machine and
`nodes.py` is its own non-agent work — gathering a run's evidence, and draining the
proposals into the deduplicated ledger. Both are this flow's alone, which is what keeps
them here rather than in [`shared/`](../shared).
"""
from __future__ import annotations

from workhorse_workflows.coder.dream.flow import Dream

__all__ = ["Dream"]
