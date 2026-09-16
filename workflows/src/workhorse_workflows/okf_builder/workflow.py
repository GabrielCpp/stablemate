"""The `okf-builder` distribution's composition root — nothing else.

`workhorse-okf-builder` is bound here (`workflows/pyproject.toml`), and this module is
what the script imports: the registry that names the distribution, folds in the node
blueprint, lists the flows a caller can run by name, and declares what a `--dry-run` gets
back from each prompt. The build graph a bare `run` starts is the flow package
[`main/`](main), and this file stays a table of contents.

The registry declares its own `package`, and that is load-bearing rather than tidy: it is
the root every prompt path renders against (`main/prompts/investigate.md`) and the name
the repo-flavor lookup uses (`.agents/flavors/okf-builder/`). Inferred from the entry
class instead, both would follow `OkfBuilder` into `main/`.
"""
from __future__ import annotations

from workhorse.cli import console_script
from workhorse.pyflow import Registry
from workhorse_workflows.okf_builder.live_audit.flow import LiveAudit
from workhorse_workflows.okf_builder.main import MAX_RESCAN_ROUNDS, MAX_STALL_ROUNDS, OkfBuilder
from workhorse_workflows.okf_builder.shared.blueprint import blueprint

workflow = (
    Registry("okf-builder", package=__package__)
    .add_blueprints(blueprint)
    .add_flows(**{"live-audit": LiveAudit})
    .stub_agents(
        {
            # Keyed by prompt STEM. Each is the reply that makes a dry run *progress*
            # past its gate; see `shared/stubs.py` for why the blank default does not.
            "investigate": {"doc_status": "documented"},
            "recheck-coverage": {"needs_journeys": False},
        }
    )
)
main = console_script(workflow.entry_point(OkfBuilder))


__all__ = ["MAX_RESCAN_ROUNDS", "MAX_STALL_ROUNDS", "OkfBuilder", "main", "workflow"]
