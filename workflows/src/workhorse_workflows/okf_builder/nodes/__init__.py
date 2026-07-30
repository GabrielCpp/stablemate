"""The okf-builder's non-agent work, grouped by subject.

Importing this package registers every node on the shared `blueprint`, which is the one
name `workflow.py` needs from here. The submodules are the subjects:

* `prepare` — where the book, the source and the drain's memory are
* `worklist` — the drain's two primitives: take an item, write back what came of it
* `checkpoint` — the mechanical convergence gate (`ostler fmt` + `doctor`) and its repairs
* `waivers` — accepting the code-fix-only defects that stall the fixup loop, with an IOU
* `coverage` — the source inventory and the join that decides whether the book covers it
* `walkthrough` — is there an app to walk, and what the book says boots it
* `stack` — booting and reaping that app and the shared CDP browser

`walkthrough` and `stack` belong to the `walkthrough-web` sub-flow (`flows/walkthrough_web.py`),
but they share this blueprint rather than getting their own: unlike author's `survey/`
package they are not a second *library* of nodes, they are the same eleven scripts the
YAML kept in one `scripts/` directory, and two of them (`select_item`, `record`) are used
by both machines against their own worklists.

Ported from `base-library/workflows/okf-builder/scripts/`. The same three things change as
in `research` and `author`, and nothing else does: the JSON envelope on stdout becomes a
**returned model**, the positional `sys.argv` entries become **typed parameters**, and a
`sys.exit(1)` becomes `raise WorkflowFailed(...)` at the *caller*. Two shapes specific to
these scripts go with them:

* the two dual-mode scripts — `boot-app.py` and `boot-browser.py`, which tore down instead
  of booting when `argv[1]` was the literal `--teardown` — become two nodes each, because
  a node is a function and the sentinel only existed so one YAML `script:` file could
  serve two nodes;
* every `ostler` subprocess becomes an `ostler` library call. `api.py` is "the *library*
  face of the `ostler` CLI … the CLI merely `json.dumps` what these return", and two of
  these scripts already called it that way while a third shelled out for the same answer.
"""
from __future__ import annotations

from workhorse_workflows.okf_builder.nodes._blueprint import blueprint
from workhorse_workflows.okf_builder.nodes.checkpoint import checkpoint_book
from workhorse_workflows.okf_builder.nodes.coverage import compute_coverage, inventory_source
from workhorse_workflows.okf_builder.nodes.prepare import prepare
from workhorse_workflows.okf_builder.nodes.stack import (
    boot_app,
    boot_browser,
    teardown_app,
    teardown_browser,
)
from workhorse_workflows.okf_builder.nodes.waivers import auto_waive
from workhorse_workflows.okf_builder.nodes.walkthrough import detect_webapp, seed_walkthrough
from workhorse_workflows.okf_builder.nodes.worklist import record, select_item

__all__ = [
    "auto_waive",
    "blueprint",
    "boot_app",
    "boot_browser",
    "checkpoint_book",
    "compute_coverage",
    "detect_webapp",
    "inventory_source",
    "prepare",
    "record",
    "seed_walkthrough",
    "select_item",
    "teardown_app",
    "teardown_browser",
]
