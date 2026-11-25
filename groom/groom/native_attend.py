from __future__ import annotations

import logging
from pathlib import Path

from groom import (
    attend,
)
from groom.models import (
    GateInfo,
    WorkflowContainer,
)

logger = logging.getLogger(__name__)



def _attend_gates(wf: WorkflowContainer, gates: list[GateInfo]) -> None:
    """Put an attendant on the gates this row reports being parked on."""
    if not wf.native:
        return
    try:
        if not wf.gates:
            attend.release(wf.container_id)
            return
        for gate in gates:
            attend.attend_gate(
                run_id=wf.container_id,
                workflow=wf.workflow_type or wf.name,
                run_dir=wf.runs_volume,
                workspace=wf.workspace_volume,
                gate_path=_gate_abs_path(wf, gate),
                question=gate.question,
                kind=gate.kind or attend.ATTENDABLE_KIND,
            )
    except Exception:
        logger.exception("attend: dispatch failed for %s", wf.container_id)


def _gate_abs_path(wf: WorkflowContainer, gate: GateInfo) -> str:
    """The gate's path on this host, for a consumer that has to open the file."""
    anchor = gate.base or wf.workspace_volume
    if not anchor:
        return gate.file_path
    return str(Path(anchor) / gate.file_path)
