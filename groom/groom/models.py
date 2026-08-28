"""Plain dataclasses shared across groom's modules — no docker/asyncio here."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# Every workhorse liveness tick. All three mean the same thing — the run's
# process is alive — and differ only in what the run is busy with: a cap sleep,
# a streaming agent turn, or any node at all (the run heartbeat, which is the
# only one a buffered script node produces). One tuple, shared by the ingest
# cache (groom.alerts) and the store's filter/prune (groom.store): the two used
# to carry private copies, and a name added to one but not the other would have
# been persisted forever or never noticed alive.
LIVENESS_METRICS = (
    "workhorse.run.heartbeat",
    "workhorse.turn.heartbeat",
    "workhorse.cap_wait.heartbeat",
)


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
    # A pyflow checkpoint can identify an older gate whose file predates the
    # canonical STATUS header. It remains answerable while that checkpoint is live.
    legacy_headerless: bool = False


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
    # For a docker row these are docker volume NAMES read via a throwaway container;
    # for a native row (``native=True``) they are plain HOST PATHS the same-host
    # groom reads directly. The consumer branches on ``native``, never on shape.
    workspace_volume: str = ""
    runs_volume: str = ""
    updated_at: str = ""
    exit_code: int | None = None
    gates: dict[str, GateInfo] = field(default_factory=dict)
    # A native (non-container) run, materialized from its own OTLP telemetry rather
    # than a docker scan/sidecar. It shares groom's host, so Files/Diff/gate reads go
    # through the local filesystem (groom.localfs) instead of docker_io, and it is
    # keyed by ``run_id`` (a host has no per-run container id). Kept out of the docker
    # prune sweep; its state is re-derived from telemetry recency (projection.is_live)
    # rather than latched, so a run that stops emitting stops reading as running and a
    # resumed one comes back.
    native: bool = False
    # "What the run is doing right now" — the workflow's per-node ``wf.activity``
    # label, shown as the row subtitle. Empty until the run stamps one.
    activity: str = ""
    # The run process's OS pid (native runs only; from the telemetry resource).
    pid: int | None = None


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
    (``first_seen_ts``).

    There is no "has finished" bit here that outlives the process: the only
    liveness question groom answers is *is it emitting right now*, and the answer
    is recomputed from these timestamps every render (``projection.is_live``).
    """

    run_id: str
    workflow: str = ""
    repo: str = ""
    branch: str = ""
    # Local-filesystem identity, denormalized off the telemetry resource. On a
    # native run these are real host paths (the dashboard row reads Files/Diff/gate
    # from them); ``native`` caches the one-time "does run_dir exist on this host?"
    # verdict so the sync path doesn't re-stat a containerized run's paths forever.
    run_dir: str = ""
    workspace: str = ""
    pid: int | None = None
    native: bool | None = None
    # The run's current `wf.activity` label — what it is doing right now — carried
    # here from the live gauges so a dashboard row can show it without waiting for a
    # span to export.
    activity: str = ""
    # Which agent CLI ran this run's most recent turn, and on which model. Read off
    # the completed `agent_turn` span rather than configured anywhere: the ladder
    # picks a backend per turn and can fall through to another one mid-run, so the
    # only honest answer to "which CLI is this run using" is the last one it used.
    # Empty until the first turn exports — a span exports on completion, so a run
    # still inside its opening turn has not advertised a CLI yet, and showing the
    # configured default there would name a harness that may never run a turn.
    backend: str = ""
    model: str = ""
    first_seen_ts: float = 0.0
    last_span_ts: float = 0.0
    # Any workhorse liveness tick (run/turn/cap-wait heartbeat) — proof the run's
    # PROCESS is alive. Its absence, not a node's slowness, is what STALL means.
    # Two clocks on purpose: ``last_heartbeat_ts`` is groom's wall clock at ingest
    # (what the STALL window measures — it must not trust a producer's skewed
    # clock), while ``last_beat_ts`` is the newest producer-stamped timestamp of a
    # liveness point — the value `groom status` prints as "last beat", matching
    # what the metric rows used to carry when heartbeats were persisted.
    last_heartbeat_ts: float = 0.0
    last_beat_ts: float = 0.0
    # Where the run is right now, straight from the node-active gauge rather than
    # inferred from the last completed span's workhorse.next. Open node spans do
    # not export, so this is the only live answer to "which node?".
    current_node: str = ""
    # How long that node has been open, as measured inside the run process.
    node_elapsed_s: float = 0.0
    # Seconds since the streaming agent last wrote a line. Small = streaming and
    # healthy however long the turn runs; climbing = wedged.
    turn_idle_s: float = 0.0
    # Lifecycle metrics make idle meaningful only while a turn is actually open.
    # None is an older producer that never emitted turn.active.
    turn_active: bool | None = None
    turn_elapsed_s: float = 0.0
    # Explicit runtime wait. Empty kind means no current wait (or an older producer).
    wait_kind: str = ""
    wait_elapsed_s: float = 0.0
    # The run's remaining gas tank, from the `workhorse.gas` gauge. None until the
    # first reading — pyflow has no tank, and a missing gauge must not read as empty.
    gas: float | None = None
    # The root span's terminal status, and the timestamp it reported. "" while the
    # run is live. Both are scoped to ONE session: a run_id is derived from the run
    # dir, so ``--resume-run`` reuses it, and an earlier session's root span must
    # not keep the new process marked dead. Any signal stamped after ``terminal_ts``
    # clears the verdict (see ``alerts._clear_stale_terminal``).
    terminal: str = ""
    terminal_ts: float = 0.0
    # Node-span repeats on the same work — the churn signal. Reset by forward
    # progress: a gas refuel, or the node re-completing under a different set of
    # workflow labels. The same node re-completing N times on the SAME work is a
    # loop whose exit condition never trips.
    node_counts: dict[str, int] = field(default_factory=dict)
    # The workflow-declared label signature each node last completed under. This
    # is what makes a repeat legible without a gas tank: pyflow has none, so a
    # drain-shaped workflow (select → work → record → select …) would otherwise
    # count its every healthy iteration as churn. The labels say which item the
    # iteration was for, so a changing signature IS the forward progress the
    # refuel counter used to report.
    node_labels: dict[str, tuple[tuple[str, str], ...]] = field(default_factory=dict)
    # Alert dedupe: rule names already fired for this run (one page per rule).
    fired: set[str] = field(default_factory=set)
