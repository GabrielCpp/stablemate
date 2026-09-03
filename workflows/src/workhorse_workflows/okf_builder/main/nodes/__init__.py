"""The non-agent work only the **main** okf-builder machine calls.

One module per subject, and each subject is reached by `workflow.py` alone — a node any
sub-flow also calls lives in [`shared/`](../shared) instead, which is what makes this
package's contents legible as "the build's own work":

* `prepare` — where the book, the source and the drain's memory are
* `waivers` — accepting the code-fix-only defects that stall the fixup loop, with an IOU
* `coverage` — the source inventory and the join that decides whether the book covers it

The drain's own primitives (`worklist`), the convergence gate (`checkpoint`), the
`blueprint` every node registers on and the stand-ins are in `shared/`, because the
`walkthrough-web` flow runs the same two primitives against its own worklist. The walk's
`walkthrough` and `stack` nodes live with the flow that calls them, in
`walkthrough_web/nodes/`.

Ported from `base-library/workflows/okf-builder/scripts/`. The same three things change as
in `research` and `author`, and nothing else does: the JSON envelope on stdout becomes a
**returned model**, the positional `sys.argv` entries become **typed parameters**, and a
`sys.exit(1)` becomes `raise WorkflowFailed(...)` at the *caller*. One shape specific to
these scripts goes with them: every `ostler` subprocess becomes an `ostler` library call.
`api.py` is "the *library* face of the `ostler` CLI … the CLI merely `json.dumps` what
these return", and two of these scripts already called it that way while a third shelled
out for the same answer.
"""
from __future__ import annotations

from workhorse_workflows.okf_builder.main.nodes.coverage import (
    advance_watermark,
    compute_coverage,
    inventory_source,
)
from workhorse_workflows.okf_builder.main.nodes.incremental import check_incremental_context
from workhorse_workflows.okf_builder.main.nodes.prepare import prepare
from workhorse_workflows.okf_builder.main.nodes.waivers import auto_waive

__all__ = [
    "advance_watermark",
    "auto_waive",
    "compute_coverage",
    "check_incremental_context",
    "inventory_source",
    "prepare",
]
