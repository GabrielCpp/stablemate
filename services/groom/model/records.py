"""What groom keeps for one pushed run, and what a reader is shown of the fleet. A run
is known by the container id its workflow pushes; its gates are the questions it is
waiting on, one per gate file."""

from __future__ import annotations

from dataclasses import dataclass, field

RUNNING = "running"
BLOCKED = "blocked"
FINISHED = "finished"
STATES = (RUNNING, BLOCKED, FINISHED)
LIVE = ("unknown", "done")
ATTEND_MODES = ("off", "headless")
GATE_STATUS = "AWAITING_OPERATOR"
PREVIEW_MAX = 140


@dataclass(frozen=True)
class Gate:
    file_path: str
    question: str


@dataclass(frozen=True)
class Run:
    container_id: str
    name: str
    repo_name: str = ""
    repo_branch: str = ""
    current_node: str = ""
    state: str = RUNNING
    exit_code: int | None = None
    gates: tuple[Gate, ...] = ()

    def __str__(self) -> str:
        return f"{self.name} [{self.state}]"

    @property
    def lifecycle(self) -> str:
        return "blocked" if self.gates else self.state

    @property
    def repo(self) -> str:
        if self.repo_name and self.repo_branch:
            return f"{self.repo_name}@{self.repo_branch}"
        return self.repo_name or "—"

    @property
    def rank(self) -> int:
        return {BLOCKED: 0, RUNNING: 2, FINISHED: 3}[self.state]

    @property
    def live(self) -> str:
        return "done" if self.state == FINISHED else "unknown"

    @property
    def live_label(self) -> str:
        return "ended" if self.state == FINISHED else ""

    @property
    def exit_hint(self) -> str:
        if self.state == FINISHED and self.exit_code is not None:
            return f"exited {self.exit_code}"
        return ""

    @property
    def gate_path(self) -> str:
        return self.gates[0].file_path if self.gates else ""


@dataclass(frozen=True)
class Ack:
    ok: bool

    def __str__(self) -> str:
        return "accepted" if self.ok else "ignored"


@dataclass(frozen=True)
class Row:
    id: str
    run_id: str
    name: str
    repo: str
    row_id: str
    state: str
    live: str
    live_label: str
    node: str
    doing: str
    gate_path: str
    gate_count: int
    exit_code: int | None
    exit_hint: str
    rank: int
    type: str = ""
    type_hue: int = 0
    silence_s: float = 0.0
    last_seen_ts: float = 0.0
    telemetry_age_s: float = 0.0
    node_elapsed_s: float = 0.0
    wait_kind: str = ""
    wait_elapsed_s: float = 0.0
    turn_active: bool | None = None
    turn_elapsed_s: float = 0.0
    turn_idle_s: float = 0.0
    mini: str = ""
    clock: None = None
    activity: str = ""
    question: str = ""
    pid: int | None = None
    native: bool = False
    sidecar: bool = False
    figures: None = None
    ended: None = None

    def __str__(self) -> str:
        bits = [self.name, self.state]
        if self.node:
            bits.append(f"in {self.node}")
        if self.gate_count:
            bits.append(f"{self.gate_count} gate(s)")
        if self.exit_hint:
            bits.append(self.exit_hint)
        return " · ".join(bits)


@dataclass(frozen=True)
class Alert:
    run_id: str
    event: str
    node: str
    question: str
    gate_path: str
    terminal: str = ""
    message: str = ""

    def __str__(self) -> str:
        return f"{self.run_id} {self.event}"


@dataclass(frozen=True)
class AttendSummary:
    mode: str
    count: int = 0
    rev: float = 0.0
    by_run: dict[str, str] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"attendant {self.mode}"


@dataclass(frozen=True)
class Counts:
    running: int = 0
    blocked: int = 0
    idle: int = 0
    finished: int = 0


@dataclass(frozen=True)
class Status:
    counts: Counts = Counts()
    repos: int = 0
    workers: int = 0


@dataclass(frozen=True)
class StoreHealth:
    ok: bool = True
    path: str = ""
    last_ok_ts: float = 0.0
    reopens: int = 0
    failures: int = 0
    last_error: str = ""
    last_error_ts: float = 0.0
    last_write_ts: float = 0.0
    last_prune_ts: float = 0.0
    wal_bytes: int = 0
    last_checkpoint_busy: int = 0


@dataclass(frozen=True)
class Fleet:
    runs: tuple[Row, ...]
    attention: tuple[Alert, ...]
    attend: AttendSummary
    type: str = "state"
    ts: float = 0.0
    v: int = 0
    scanning: bool = False
    status: Status = Status()
    store: StoreHealth = StoreHealth()

    def __str__(self) -> str:
        return f"{len(self.runs)} run(s)"


@dataclass(frozen=True)
class GateView:
    file_path: str
    question: str
    preview: str
    status: str = GATE_STATUS
    kind: str = ""


@dataclass(frozen=True)
class Running:
    node: str
    elapsed_s: float = 0.0
    wait_kind: str = ""
    wait_elapsed_s: float = 0.0
    since_ts: float = 0.0
    node_since_ts: float = 0.0


@dataclass(frozen=True)
class Strip:
    node: str
    kind: str = "node"
    wait_kind: str = ""
    started_ts: float = 0.0
    node_since_ts: float = 0.0
    idle_since_ts: float | None = None
    beat_ts: float | None = None
    norm: None = None


@dataclass(frozen=True)
class Head:
    id: str
    handle: str
    state: str
    repo: str
    live: str
    live_label: str
    node: str
    exit_hint: str
    exit_ok: bool
    type: str = ""
    type_hue: int = 0
    pid: int | None = None
    cli: str = ""
    activity: str = ""
    worktree: str = ""
    checkout: str = ""
    last_seen_ts: float = 0.0


@dataclass(frozen=True)
class Metrics:
    empty: bool = True
    cells: tuple[str, ...] = ()
    alerts: tuple[str, ...] = ()
    run_dir: str = ""


@dataclass(frozen=True)
class Worker:
    found: bool
    id: str
    run_id: str | None = None
    state: str | None = None
    node: str | None = None
    gates: tuple[GateView, ...] | None = None
    running: Running | None = None
    strip: Strip | None = None
    ended: None = None
    head: Head | None = None
    metrics: Metrics | None = None
    logs: tuple[str, ...] | None = None
    history: tuple[str, ...] | None = None
    figures_rev: int | None = None
    activity_rev: int | None = None
    metrics_rev: int | None = None

    def __str__(self) -> str:
        if not self.found:
            return f"no run {self.id}"
        return f"{self.id} {self.state}"


@dataclass(frozen=True)
class AttendSettings:
    mode: str
    last_mode: str = "headless"
    cli: str = "claude"
    deny: tuple[str, ...] = ()
    sources: dict[str, str] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"attendant {self.mode}"


@dataclass(frozen=True)
class Line:
    """One run as the dashboard's run list shows it."""

    id: str
    state: str
    live: str
    repo: str
    row_id: str
    live_label: str
    doing: str

    def __str__(self) -> str:
        bits = [self.id, self.state, self.repo]
        if self.doing:
            bits.append(self.doing)
        if self.live_label:
            bits.append(self.live_label)
        return " · ".join(bits)


@dataclass(frozen=True)
class Panel:
    """What the settings pane shows of the attendant."""

    attendant: str

    def __str__(self) -> str:
        return f"attendant {self.attendant}"


@dataclass(frozen=True)
class Filter:
    """The text typed in the run list's filter box."""

    key: str
    text: str


@dataclass(frozen=True)
class Session:
    """An attendant's session, which only an attendant creates."""

    session_id: str


@dataclass(frozen=True)
class Job:
    """An attendant job, which only a gate waiting on an attendant creates."""

    job_id: str


@dataclass(frozen=True)
class Item:
    """An item of a dispatch queue, which only a configured queue takes."""

    item_id: str
