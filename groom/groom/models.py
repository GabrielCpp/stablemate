"""Plain dataclasses shared across groom's modules — no docker/asyncio here."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class WorkflowState(str, Enum):
    RUNNING = "running"
    BLOCKED = "blocked"
    IDLE = "idle"
    FINISHED = "finished"


@dataclass
class GateInfo:
    """A single live operator gate — one per blocked context file.

    A workflow can have more than one gate file matching
    ``STATUS: AWAITING_OPERATOR`` at once (rare, but the graph doesn't forbid
    it), so gates are keyed by their repo-relative file path, not assumed to
    be singular per workflow.
    """

    workflow_id: str
    file_path: str
    question: str = ""
    status: str = "AWAITING_OPERATOR"


@dataclass
class WorkflowContainer:
    container_id: str
    name: str
    repo_name: str = ""
    repo_branch: str = ""
    workflow_type: str = ""
    state: WorkflowState = WorkflowState.IDLE
    current_node: str = ""
    run_id: str = ""
    workspace_volume: str = ""
    runs_volume: str = ""
    updated_at: str = ""
    exit_code: int | None = None
    gates: dict[str, GateInfo] = field(default_factory=dict)


@dataclass
class AnswerResult:
    ok: bool
    message: str = ""
