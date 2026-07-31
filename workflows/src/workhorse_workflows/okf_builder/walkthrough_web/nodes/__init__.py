"""The non-agent work only the `walkthrough-web` flow calls.

* `walkthrough` — is there an app to walk, and what the book says boots it
* `stack` — booting and reaping that app and the shared CDP browser

These register on the same `shared.blueprint` as every other node rather than getting one
of their own: unlike author's `survey/` package they are not a second *library*, they are
the same scripts the YAML kept in one `scripts/` directory. What is different now is where
they *live* — beside the flow that is their only caller, so the walk is one directory
rather than two halves named the same thing in `flows/` and `nodes/`.

The two primitives the walk shares with the build — `select_item` and `record`, run
against its own worklist — stay in [`shared/`](../../shared) for exactly that reason.
"""
from __future__ import annotations

from workhorse_workflows.okf_builder.walkthrough_web.nodes.stack import (
    boot_app,
    boot_browser,
    teardown_app,
    teardown_browser,
)
from workhorse_workflows.okf_builder.walkthrough_web.nodes.walkthrough import (
    detect_webapp,
    seed_walkthrough,
)

__all__ = [
    "boot_app",
    "boot_browser",
    "detect_webapp",
    "seed_walkthrough",
    "teardown_app",
    "teardown_browser",
]
