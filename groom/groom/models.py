"""Plain dataclasses shared across groom's modules — no docker/asyncio here."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


LIVENESS_METRICS = (
    "workhorse.run.heartbeat",
    "workhorse.turn.heartbeat",
    "workhorse.cap_wait.heartbeat",
)

UNARCHIVED_DELETABLE_METRICS = (
    "workhorse.node.active",
    "workhorse.node.elapsed_s",
    "workhorse.turn.active",
    "workhorse.turn.idle_s",
    "workhorse.turn.elapsed_s",
    "workhorse.wait.active",
    "workhorse.wait.elapsed_s",
)

ARCHIVED_METRICS = (
    "workhorse.gas",
    "workhorse.gas.capacity",
    "workhorse.gas.refuels",
    "workhorse.cap_wait.remaining_s",
)


class WorkflowState(str, Enum):
    RUNNING = "running"
    BLOCKED = "blocked"
    IDLE = "idle"
    FINISHED = "finished"


@dataclass
class GateInfo:
    """A single live operator gate — one per blocked context file."""

    workflow_id: str
    file_path: str
    question: str = ""
    status: str = "AWAITING_OPERATOR"
    base: str = ""
    legacy_headerless: bool = False
    kind: str = ""


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
    native: bool = False
    activity: str = ""
    pid: int | None = None
    last_session: tuple[int, str] | None = None


@dataclass
class AnswerResult:
    ok: bool
    message: str = ""


@dataclass
class RunTelemetry:
    """Per-run alert-rule state, updated on every OTLP ingest (the hot cache beside the durable SQLite store)."""

    run_id: str
    workflow: str = ""
    repo: str = ""
    branch: str = ""
    run_dir: str = ""
    workspace: str = ""
    pid: int | None = None
    native: bool | None = None
    activity: str = ""
    backend: str = ""
    model: str = ""
    first_seen_ts: float = 0.0
    last_span_ts: float = 0.0
    last_heartbeat_ts: float = 0.0
    last_beat_ts: float = 0.0
    current_node: str = ""
    node_elapsed_s: float = 0.0
    turn_idle_s: float = 0.0
    turn_active: bool | None = None
    turn_elapsed_s: float = 0.0
    wait_kind: str = ""
    wait_elapsed_s: float = 0.0
    wait_series: tuple[tuple[str, str], ...] | None = None
    closed_wait_series: set[tuple[tuple[str, str], ...]] = field(default_factory=set)
    wait_gate_path: str = ""
    wait_gate_question: str = ""
    last_telemetry_ts: float = 0.0
    last_session: tuple[int, str] | None = None
    gas: float | None = None
    terminal: str = ""
    terminal_ts: float = 0.0
    node_counts: dict[str, int] = field(default_factory=dict)
    node_labels: dict[str, tuple[tuple[str, str], ...]] = field(default_factory=dict)
    fired: set[str] = field(default_factory=set)
