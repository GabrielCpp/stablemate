"""What groom answers beyond the fleet: the reads of one run's telemetry, of its files and
inbox, of the attendant's queue and log and of the dispatch queues. The book's groom has
a fresh database and no volumes, so every one of these says what an empty store says."""

from __future__ import annotations

from dataclasses import dataclass, field

EXTENSIONS_BY_LANGUAGE = {
    "javascript": "js mjs cjs jsx",
    "typescript": "ts tsx",
    "python": "py",
    "ruby": "rb",
    "go": "go",
    "rust": "rs",
    "java": "java",
    "kotlin": "kt",
    "c": "c h",
    "cpp": "cpp cc hpp",
    "csharp": "cs",
    "php": "php",
    "swift": "swift",
    "scala": "scala",
    "bash": "sh bash zsh",
    "yaml": "yml yaml",
    "json": "json",
    "ini": "toml ini cfg",
    "markdown": "md markdown",
    "xml": "html xml svg vue",
    "css": "css",
    "scss": "scss",
    "less": "less",
    "sql": "sql",
    "lua": "lua",
    "perl": "pl",
    "r": "r",
    "dart": "dart",
}

LANGUAGES = {
    extension: language
    for language, extensions in EXTENSIONS_BY_LANGUAGE.items()
    for extension in extensions.split()
}

ENDINGS = (
    ("success", "success"),
    ("gave-up", "gave up"),
    ("failed", "failed"),
    ("interrupted", "interrupted"),
    ("crashed", "crashed"),
    ("none", "no ending recorded"),
)


def language_of(path: str) -> str:
    """The highlight.js language of a path, by extension, or by whole name for a Dockerfile and a Makefile."""
    base = path.split("/")[-1].lower()
    if base == "dockerfile":
        return "dockerfile"
    if base == "makefile":
        return "makefile"
    _, dot, ext = base.rpartition(".")
    return LANGUAGES.get(ext, "") if dot else ""


@dataclass(frozen=True)
class Outbox:
    found: bool
    file_path: str | None = None
    question: str | None = None
    status: str | None = None

    def __str__(self) -> str:
        return f"gate {self.file_path}" if self.found else "no gate"


@dataclass(frozen=True)
class Notice:
    ok: bool
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class Inbox:
    messages: tuple[str, ...] = ()

    def __str__(self) -> str:
        return "no messages"


@dataclass(frozen=True)
class Tree:
    paths: tuple[str, ...] = ()
    failed: bool = True
    reported: bool = True
    served: str = "volume"
    repos: tuple[str, ...] | None = None


@dataclass(frozen=True)
class FileText:
    path: str
    lang: str
    content: str = ""
    failed: bool = True
    reported: bool = True
    served: str = "volume"


@dataclass(frozen=True)
class Change:
    diff: str = ""
    untracked: tuple[str, ...] = ()
    failed: bool = True
    reported: bool = True
    served: str = "volume"
    repos: tuple[str, ...] | None = None
    based: bool | None = None
    base: str | None = None
    base_ref: str | None = None
    base_branch: str | None = None
    base_reason: str | None = None


@dataclass(frozen=True)
class Refreshed:
    ok: bool = True
    count: int = 0


@dataclass(frozen=True)
class Reloaded:
    ok: bool = True
    reloaded: int = 0


@dataclass(frozen=True)
class Done:
    ok: bool = False


@dataclass(frozen=True)
class Cost:
    turns: int = 0
    priced_turns: int = 0
    reports_cost: bool = False
    usd: float | None = None
    est_usd: float | None = None
    output_tokens: int = 0
    backends: tuple[str, ...] = ()


@dataclass(frozen=True)
class Tiles:
    finished: bool = False
    reports_cost: bool = False
    cost_usd: float | None = None
    turns: int = 0
    priced_turns: int = 0
    active_s: float = 0.0
    items_done: int | None = None
    items_total: int | None = None
    est_usd: float | None = None
    backends: tuple[str, ...] = ()
    wall_s: float = 0.0
    sessions: int = 0


@dataclass(frozen=True)
class Standing:
    gates: int = 0
    gate_wait_s: float = 0.0
    failed_steps: int = 0
    retries: int = 0
    failed_gate_checks: int = 0
    churn_alerts: int = 0
    problems: int = 0


@dataclass(frozen=True)
class Facts:
    started_ts: float | None = None
    branch: str = ""
    run_dir: str = ""


@dataclass(frozen=True)
class Overview:
    run_id: str
    finished: bool = False
    cost: Cost = Cost()
    figures: Tiles = Tiles()
    standing: Standing = Standing()
    flows: tuple[dict[str, str], ...] = ()
    nodes: tuple[dict[str, str], ...] = ()
    compare: dict[str, str] | None = None
    norm_runs: int = 0
    items: dict[str, str] | None = None
    time_s: float = 0.0
    clock: dict[str, str] | None = None
    models: tuple[str, ...] = ()
    sessions: tuple[dict[str, str], ...] = ()
    facts: Facts = Facts()
    as_of_ts: float | None = None
    ending: dict[str, str] | None = None

    def __str__(self) -> str:
        return f"overview of {self.run_id}"


@dataclass(frozen=True)
class Totals:
    runs: int = 0
    reading: int = 0
    unreadable: int = 0
    spent_usd: float = 0.0
    estimate_usd: float = 0.0
    partly_priced: int = 0
    active_s: float = 0.0
    ready: int = 0
    success: int = 0


@dataclass(frozen=True)
class History:
    runs: tuple[dict[str, str], ...] = ()
    totals: Totals = Totals()
    medians: dict[str, str] = field(default_factory=dict)
    endings: tuple[tuple[str, str], ...] = ENDINGS
    unlisted: int = 0

    def __str__(self) -> str:
        return "the history of ended runs"


@dataclass(frozen=True)
class Activity:
    run_id: str
    rows: tuple[dict[str, str], ...] = ()
    items: tuple[dict[str, str], ...] = ()
    problems: int = 0
    log_count: int = 0
    as_of: float = 0.0

    def __str__(self) -> str:
        return f"activity of {self.run_id}"


@dataclass(frozen=True)
class Records:
    run_id: str
    metrics: bool = False
    records: tuple[dict[str, str], ...] = ()
    total: int = 0
    metric_samples: int = 0
    next: str = ""

    def __str__(self) -> str:
        return f"records of {self.run_id}"


@dataclass(frozen=True)
class Matches:
    run_id: str
    query: str = ""
    matches: tuple[dict[str, str], ...] = ()

    def __str__(self) -> str:
        return f"matches of {self.query}"


@dataclass(frozen=True)
class AttendQueue:
    mode: str
    jobs: tuple[dict[str, str], ...] = ()

    def __str__(self) -> str:
        return f"attendant {self.mode}, no job"


@dataclass(frozen=True)
class AttendSessions:
    mode: str
    sessions: tuple[dict[str, str], ...] = ()

    def __str__(self) -> str:
        return f"attendant {self.mode}, no session"


@dataclass(frozen=True)
class AttendSession:
    session_id: str
    resume: str
    present: bool = False
    path: str = ""
    entries: tuple[dict[str, str], ...] = ()
    record: dict[str, str] | None = None
    attempts: tuple[str, ...] = ()

    def __str__(self) -> str:
        return f"session {self.session_id}"


@dataclass(frozen=True)
class Queues:
    queues: tuple[dict[str, str], ...] = ()

    def __str__(self) -> str:
        return "no dispatch queue"


@dataclass(frozen=True)
class QueueItems:
    items: tuple[dict[str, str], ...] = ()

    def __str__(self) -> str:
        return "no queued item"
