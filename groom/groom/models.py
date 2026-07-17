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


@dataclass
class RunTelemetry:
    """Per-run alert-rule state, updated on every OTLP ingest (the hot cache
    beside the durable SQLite store). Spans export on COMPLETION, so "the run
    ended" is signalled by the root ``run:*`` span arriving (``terminal``), and
    "the run started" is approximated by the first span/metric seen
    (``first_seen_ts``) — good enough for the BUDGET clock.
    """

    run_id: str
    workflow: str = ""
    repo: str = ""
    branch: str = ""
    first_seen_ts: float = 0.0
    last_span_ts: float = 0.0
    # Any workhorse liveness tick (run/turn/cap-wait heartbeat) — proof the run's
    # PROCESS is alive. Its absence, not a node's slowness, is what STALL means.
    last_heartbeat_ts: float = 0.0
    # Where the run is right now, straight from the node-active gauge rather than
    # inferred from the last completed span's workhorse.next. Open node spans do
    # not export, so this is the only live answer to "which node?".
    current_node: str = ""
    # How long that node has been open, as measured inside the run process.
    node_elapsed_s: float = 0.0
    # Seconds since the streaming agent last wrote a line. Small = streaming and
    # healthy however long the turn runs; climbing = wedged.
    turn_idle_s: float = 0.0
    terminal: str = ""  # root span's terminal status; "" while the run is live
    # Node-span repeats since the last gas refuel — the churn signal. A refuel
    # (forward progress) resets it; the same node re-completing N times on one
    # tank is a loop that will burn gas for hours before the tank trips.
    node_counts: dict[str, int] = field(default_factory=dict)
    # Alert dedupe: rule names already fired for this run (one page per rule).
    fired: set[str] = field(default_factory=set)
