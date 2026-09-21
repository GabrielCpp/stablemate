"""The `okf-builder` distribution's composition root — nothing else."""
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
            "investigate": {"doc_status": "documented"},
            "recheck-coverage": {"needs_journeys": False},
        }
    )
)
main = console_script(workflow.entry_point(OkfBuilder))


__all__ = ["MAX_RESCAN_ROUNDS", "MAX_STALL_ROUNDS", "OkfBuilder", "main", "workflow"]
