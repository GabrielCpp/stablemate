"""Embedded SQLite persistence for telemetry — the durable, searchable half of groom's collector role (stdlib ``sqlite3``, no database server)."""

from __future__ import annotations

import functools
import json
import logging
import os
import re
import sqlite3
import tempfile
import threading
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, ParamSpec, TypeVar

from platformdirs import user_data_dir

from groom import prices
from groom.models import (
    ARCHIVED_METRICS,
    LIVENESS_METRICS,
    UNARCHIVED_DELETABLE_METRICS,
)

logger = logging.getLogger(__name__)

RETENTION_DAYS = float(os.environ.get("GROOM_RETENTION_DAYS", "30"))
ACTIVE_WINDOW_S = float(os.environ.get("GROOM_ACTIVE_WINDOW_S", "86400"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS spans (
    span_id   TEXT PRIMARY KEY,
    trace_id  TEXT NOT NULL,
    parent_id TEXT NOT NULL DEFAULT '',
    run_id    TEXT NOT NULL DEFAULT '',
    workflow  TEXT NOT NULL DEFAULT '',
    repo      TEXT NOT NULL DEFAULT '',
    branch    TEXT NOT NULL DEFAULT '',
    node      TEXT NOT NULL DEFAULT '',
    name      TEXT NOT NULL DEFAULT '',
    run_dir   TEXT NOT NULL DEFAULT '',
    start_ts  REAL NOT NULL,
    end_ts    REAL NOT NULL,
    status    TEXT NOT NULL DEFAULT 'UNSET',
    attrs_json TEXT NOT NULL DEFAULT '{}',
    duration_ms INTEGER,
    total_cost_usd REAL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cache_read_tokens INTEGER,
    cache_creation_tokens INTEGER,
    pid INTEGER,
    resume_generation INTEGER,
    head_start TEXT,
    head_end TEXT,
    workspace_start TEXT,
    workspace_end TEXT,
    vcs_start TEXT,
    vcs_end TEXT,
    origin_start TEXT,
    origin_end TEXT,
    branch_start TEXT,
    branch_end TEXT,
    repositories_start TEXT,
    repositories_end TEXT
);
CREATE INDEX IF NOT EXISTS spans_run ON spans(run_id, start_ts);
CREATE INDEX IF NOT EXISTS spans_node ON spans(node);
CREATE INDEX IF NOT EXISTS spans_status ON spans(status);
CREATE INDEX IF NOT EXISTS spans_start ON spans(start_ts DESC);
CREATE INDEX IF NOT EXISTS spans_summary
    ON spans(run_id, end_ts, workflow, repo, start_ts, status);
CREATE TABLE IF NOT EXISTS metrics (
    run_id TEXT NOT NULL DEFAULT '',
    name   TEXT NOT NULL,
    ts     REAL NOT NULL,
    value  REAL NOT NULL,
    attrs_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS metrics_run ON metrics(run_id, name, ts);
-- Series-major, for the one sweep that is not run-major: prune deletes the
-- never-archived gauges by name across every run, and metrics_run cannot serve
-- that — `name` is not its leading column, so the sweep degraded into a full
-- scan of the largest table in the file, once per chunk. Measured at 350s on a
-- 1 GB store; an index range scan instead.
CREATE INDEX IF NOT EXISTS metrics_name_ts ON metrics(name, ts);
CREATE TABLE IF NOT EXISTS logs (
    run_id   TEXT NOT NULL DEFAULT '',
    workflow TEXT NOT NULL DEFAULT '',
    run_dir  TEXT NOT NULL DEFAULT '',
    node     TEXT NOT NULL DEFAULT '',
    logger   TEXT NOT NULL DEFAULT '',
    severity TEXT NOT NULL DEFAULT 'INFO',
    body     TEXT NOT NULL DEFAULT '',
    ts       REAL NOT NULL,
    trace_id TEXT NOT NULL DEFAULT '',
    attrs_json TEXT NOT NULL DEFAULT '{}',
    head     TEXT,
    workspace TEXT,
    vcs TEXT,
    origin TEXT,
    branch TEXT,
    repositories TEXT
);
CREATE INDEX IF NOT EXISTS logs_run ON logs(run_id, ts);
CREATE INDEX IF NOT EXISTS logs_node ON logs(run_id, node, ts);
CREATE INDEX IF NOT EXISTS logs_severity ON logs(severity);
CREATE TABLE IF NOT EXISTS turns (
    run_id     TEXT NOT NULL DEFAULT '',
    workflow   TEXT NOT NULL DEFAULT '',
    flow       TEXT NOT NULL DEFAULT '',
    node       TEXT NOT NULL DEFAULT '',
    session_id TEXT NOT NULL DEFAULT '',
    generation INTEGER,
    seq        INTEGER,
    ts         REAL NOT NULL DEFAULT 0,
    backend    TEXT NOT NULL DEFAULT '',
    source     TEXT NOT NULL DEFAULT '',
    path       TEXT NOT NULL DEFAULT '',
    bytes      INTEGER NOT NULL DEFAULT 0,
    sha256     TEXT NOT NULL DEFAULT '',
    head       TEXT,
    PRIMARY KEY (run_id, generation, seq, session_id)
);
CREATE INDEX IF NOT EXISTS turns_visit ON turns(run_id, node, generation, seq);
CREATE INDEX IF NOT EXISTS turns_session ON turns(session_id);
CREATE TABLE IF NOT EXISTS attend_sessions (
    job_id         TEXT PRIMARY KEY,
    run_id         TEXT NOT NULL DEFAULT '',
    workflow       TEXT NOT NULL DEFAULT '',
    run_dir        TEXT NOT NULL DEFAULT '',
    workspace      TEXT NOT NULL DEFAULT '',
    kind           TEXT NOT NULL DEFAULT '',
    reason         TEXT NOT NULL DEFAULT '',
    node           TEXT NOT NULL DEFAULT '',
    gate_path      TEXT NOT NULL DEFAULT '',
    status         TEXT NOT NULL DEFAULT 'running',
    session_ids    TEXT NOT NULL DEFAULT '',
    pid            INTEGER,
    exit_code      INTEGER,
    started_at     REAL NOT NULL DEFAULT 0,
    ended_at       REAL,
    released_state TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS attend_recent ON attend_sessions(started_at DESC);
CREATE INDEX IF NOT EXISTS attend_run ON attend_sessions(run_id, status);
CREATE TABLE IF NOT EXISTS dispatch_items (
    item_id       TEXT PRIMARY KEY,
    queue         TEXT NOT NULL DEFAULT '',
    command       TEXT NOT NULL DEFAULT '',
    params        TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'pending',
    run_id        TEXT NOT NULL DEFAULT '',
    pid           INTEGER,
    exit_code     INTEGER,
    enqueued_at   REAL NOT NULL DEFAULT 0,
    started_at    REAL,
    ended_at      REAL
);
CREATE INDEX IF NOT EXISTS dispatch_queue_status ON dispatch_items(queue, status);
CREATE INDEX IF NOT EXISTS dispatch_recent ON dispatch_items(enqueued_at DESC);
"""


def db_path() -> Path:
    """``$GROOM_DB`` (tests point it at a temp file), else the platform data dir — read per call so a test's env var takes effect without reimport."""
    env = os.environ.get("GROOM_DB")
    if env:
        return Path(env)
    return Path(user_data_dir("groom")) / "groom.db"


_ADDED_SPAN_COLUMNS = (
    ("run_dir", "TEXT NOT NULL DEFAULT ''"),
    ("duration_ms", "INTEGER"),
    ("total_cost_usd", "REAL"),
    ("input_tokens", "INTEGER"),
    ("output_tokens", "INTEGER"),
    ("cache_read_tokens", "INTEGER"),
    ("cache_creation_tokens", "INTEGER"),
    ("pid", "INTEGER"),
    ("resume_generation", "INTEGER"),
    ("head_start", "TEXT"),
    ("head_end", "TEXT"),
    ("workspace_start", "TEXT"),
    ("workspace_end", "TEXT"),
    ("vcs_start", "TEXT"),
    ("vcs_end", "TEXT"),
    ("origin_start", "TEXT"),
    ("origin_end", "TEXT"),
    ("branch_start", "TEXT"),
    ("branch_end", "TEXT"),
    ("repositories_start", "TEXT"),
    ("repositories_end", "TEXT"),
    ("est_cost_usd", "REAL"),
    ("priced_model", "TEXT"),
)

_ADDED_LOG_COLUMNS = (
    ("head", "TEXT"),
    ("workspace", "TEXT"),
    ("vcs", "TEXT"),
    ("origin", "TEXT"),
    ("branch", "TEXT"),
    ("repositories", "TEXT"),
)

_PROMOTED_SPAN_COLUMNS = (
    ("duration_ms", "duration_ms", int),
    ("total_cost_usd", "total_cost_usd", float),
    ("usage.input_tokens", "input_tokens", int),
    ("usage.output_tokens", "output_tokens", int),
    ("usage.cache_read_input_tokens", "cache_read_tokens", int),
    ("usage.cache_creation_input_tokens", "cache_creation_tokens", int),
    ("git.head.start", "head_start", str),
    ("git.head.end", "head_end", str),
    ("workspace.path.start", "workspace_start", str),
    ("workspace.path.end", "workspace_end", str),
    ("workspace.vcs.start", "vcs_start", str),
    ("workspace.vcs.end", "vcs_end", str),
    ("git.origin.start", "origin_start", str),
    ("git.origin.end", "origin_end", str),
    ("git.branch.start", "branch_start", str),
    ("git.branch.end", "branch_end", str),
    ("workhorse.repositories.start", "repositories_start", str),
    ("workhorse.repositories.end", "repositories_end", str),
)

_PROMOTED_SPAN_FIELDS = ("pid", "resume_generation")

_DERIVED_SPAN_COLUMNS = ("est_cost_usd", "priced_model")

_SPAN_VALUE_COLUMNS = (
    *(column for _key, column, _cast in _PROMOTED_SPAN_COLUMNS),
    *_PROMOTED_SPAN_FIELDS,
    *_DERIVED_SPAN_COLUMNS,
)


def _promoted(span: dict[str, Any], attrs: dict[str, Any]) -> tuple[Any, ...]:
    """The promoted and derived columns' values for one span, in `_SPAN_VALUE_COLUMNS` order."""
    values: dict[str, Any] = {}
    for key, column, cast in _PROMOTED_SPAN_COLUMNS:
        raw = attrs.get(key)
        try:
            values[column] = None if raw is None or isinstance(raw, bool) else cast(raw)
        except (TypeError, ValueError):
            values[column] = None
    for field in _PROMOTED_SPAN_FIELDS:
        raw = span.get(field)
        try:
            values[field] = None if raw is None else int(raw)
        except (TypeError, ValueError):
            values[field] = None
    model = str(attrs.get("model") or "")
    values["est_cost_usd"] = _estimated(model, values)
    values["priced_model"] = model if values["est_cost_usd"] is not None else None
    return tuple(values[column] for column in _SPAN_VALUE_COLUMNS)


def _estimated(model: str, tokens: dict[str, Any]) -> float | None:
    """This turn's tokens at the rate card, or NULL when the model is not in it."""
    return prices.estimate(
        model,
        tokens.get("input_tokens"),
        tokens.get("output_tokens"),
        tokens.get("cache_read_tokens"),
        tokens.get("cache_creation_tokens"),
    )


_ADDED_ATTEND_COLUMNS: tuple[tuple[str, str], ...] = ()

_ADDED_DISPATCH_COLUMNS: tuple[tuple[str, str], ...] = ()


def _migrate(conn: sqlite3.Connection) -> None:
    for table, added in (
        ("spans", _ADDED_SPAN_COLUMNS),
        ("logs", _ADDED_LOG_COLUMNS),
        ("attend_sessions", _ADDED_ATTEND_COLUMNS),
        ("dispatch_items", _ADDED_DISPATCH_COLUMNS),
    ):
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for column, decl in added:
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")  # noqa: S608


_P = ParamSpec("_P")
_T = TypeVar("_T")

REOPEN_COOLDOWN_S = 5.0


@dataclass(frozen=True, slots=True)
class StoreHealth:
    """What the store would say if asked whether it is still storing."""

    ok: bool
    path: str
    last_ok_ts: float
    reopens: int
    failures: int
    last_error: str
    last_error_ts: float
    last_write_ts: float
    last_prune_ts: float
    wal_bytes: int
    last_checkpoint_busy: int


class _Store:
    """The process's one SQLite handle, and the discipline that keeps it usable."""

    def __init__(self, monotonic: Callable[[], float] = time.monotonic) -> None:
        self.monotonic = monotonic
        self.lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._path: Path | None = None
        self._readers = threading.local()
        self._generation = 0
        self._reopens = 0
        self._failures = 0
        self._last_error = ""
        self._last_error_ts = 0.0
        self._last_reopen_at = 0.0
        self._last_ok_ts = 0.0
        self._last_write_ts = 0.0
        self._last_prune_ts = 0.0
        self._last_checkpoint_busy = 0

    def connect(self) -> sqlite3.Connection:
        """The open connection, opening (or reopening) it if there isn't one."""
        with self.lock:
            path = db_path()
            if self._conn is not None and self._path != path:
                self._close_quietly()
            if self._conn is None:
                self._conn = self._open(path)
                self._path = path
            return self._conn

    def _open(self, path: Path) -> sqlite3.Connection:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.executescript(_SCHEMA)
        _migrate(conn)
        return conn

    @contextmanager
    def writing(self) -> Iterator[sqlite3.Connection]:
        """One atomic write."""
        with self.lock:
            conn = self.connect()
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                with suppress(sqlite3.Error):
                    conn.rollback()
                raise
            conn.commit()
            self._last_write_ts = time.time()

    def recycle(self, exc: BaseException, where: str) -> None:
        """Throw the handle away so the next call opens a fresh one."""
        with self.lock:
            self._failures += 1
            self._last_error = f"{type(exc).__name__}: {exc}"
            self._last_error_ts = time.time()
            now = self.monotonic()
            if self._reopens and now - self._last_reopen_at < REOPEN_COOLDOWN_S:
                logger.error(
                    "groom.store: %s failed again while cooling down: %s", where, exc
                )
                raise exc
            self._close_quietly()
            self._reopens += 1
            self._last_reopen_at = now
            logger.error(
                "groom.store: recycling the connection after %s in %s", exc, where
            )

    def reset(self) -> None:
        """Close the connection and forget every failure with it (tests switch ``$GROOM_DB`` between cases, and a counter that survived would be another case's)."""
        with self.lock:
            self._close_quietly()
            self.retire_reader()
            self._path = None
            self._reopens = 0
            self._failures = 0
            self._last_error = ""
            self._last_error_ts = 0.0
            self._last_reopen_at = 0.0
            self._last_ok_ts = 0.0
            self._last_write_ts = 0.0
            self._last_prune_ts = 0.0
            self._last_checkpoint_busy = 0

    def _close_quietly(self) -> None:
        if self._conn is not None:
            with suppress(sqlite3.Error):
                self._conn.rollback()
            with suppress(sqlite3.Error):
                self._conn.close()
        self._conn = None
        self._generation += 1

    def read_connection(self) -> sqlite3.Connection:
        """A read-only connection belonging to the calling thread."""
        path = db_path()
        cached: _Reader | None = getattr(self._readers, "handle", None)
        if (
            cached is not None
            and cached.generation == self._generation
            and cached.path == path
        ):
            return cached.conn
        self.retire_reader()
        with self.lock:
            self.connect()
            if not (self._path or path).exists():
                self._close_quietly()
                self.connect()
            generation, opened = self._generation, self._path or path
        conn = sqlite3.connect(opened, check_same_thread=False, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA query_only=1")
        self._readers.handle = _Reader(conn, generation, opened)
        return conn

    def retire_reader(self) -> None:
        """Drop this thread's read handle; its next query opens a fresh one."""
        cached: _Reader | None = getattr(self._readers, "handle", None)
        self._readers.handle = None
        if cached is not None:
            with suppress(sqlite3.Error):
                cached.conn.close()

    def recycle_reader(self, exc: BaseException, where: str) -> None:
        """A read failed: retire that handle, and leave the writer alone."""
        self._failures += 1
        self._last_error = f"{type(exc).__name__}: {exc}"
        self._last_error_ts = time.time()
        logger.error("groom.store: retiring the read handle after %s in %s", exc, where)
        self.retire_reader()

    def note_ok(self) -> None:
        """Stamp a statement that ran."""
        self._last_ok_ts = time.time()

    def note_prune(self, ts: float | None = None) -> None:
        self._last_prune_ts = ts if ts is not None else time.time()

    def note_checkpoint(self, busy: int) -> None:
        self._last_checkpoint_busy = busy

    def health(self) -> StoreHealth:
        path = db_path()
        wal = path.with_name(path.name + "-wal")
        wal_bytes = wal.stat().st_size if wal.exists() else 0
        return StoreHealth(
            ok=self._last_error_ts <= self._last_ok_ts,
            path=str(path),
            last_ok_ts=self._last_ok_ts,
            reopens=self._reopens,
            failures=self._failures,
            last_error=self._last_error,
            last_error_ts=self._last_error_ts,
            last_write_ts=self._last_write_ts,
            last_prune_ts=self._last_prune_ts,
            wal_bytes=wal_bytes,
            last_checkpoint_busy=self._last_checkpoint_busy,
        )


@dataclass(slots=True)
class _Reader:
    """One thread's read handle, tagged with what it was opened against."""

    conn: sqlite3.Connection
    generation: int
    path: Path


_STORE = _Store()


def _resilient(fn: Callable[_P, _T]) -> Callable[_P, _T]:
    """Serialize a store call, and heal the connection under it exactly once."""

    name = getattr(fn, "__name__", "store call")

    @functools.wraps(fn)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _T:
        with _STORE.lock:
            try:
                result = fn(*args, **kwargs)
            except sqlite3.Error as exc:
                _STORE.recycle(exc, name)
            else:
                _STORE.note_ok()
                return result
            result = fn(*args, **kwargs)
            _STORE.note_ok()
            return result

    return wrapper


def _reading(fn: Callable[_P, _T]) -> Callable[_P, _T]:
    """:func:`_resilient` for a query: heal once, and take no lock doing it."""
    name = getattr(fn, "__name__", "store read")

    @functools.wraps(fn)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _T:
        try:
            result = fn(*args, **kwargs)
        except sqlite3.Error as exc:
            _STORE.recycle_reader(exc, name)
        else:
            _STORE.note_ok()
            return result
        result = fn(*args, **kwargs)
        _STORE.note_ok()
        return result

    return wrapper


def _noop_on_empty(zero: Any) -> Callable[[Callable[_P, _T]], Callable[_P, _T]]:
    """Answer a batch with nothing in it *before* :func:`_resilient` takes the lock."""

    def decorate(fn: Callable[_P, _T]) -> Callable[_P, _T]:
        @functools.wraps(fn)
        def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _T:
            if args and not args[0]:
                return zero
            return fn(*args, **kwargs)

        return wrapper

    return decorate


def _connection() -> sqlite3.Connection:
    return _STORE.connect()


def _read_connection() -> sqlite3.Connection:
    return _STORE.read_connection()


def reset() -> None:
    """Close the module connection so the next call reopens (tests switch GROOM_DB between cases)."""
    _STORE.reset()


def health() -> StoreHealth:
    """Whether the collector is still storing what it is told, and since when."""
    return _STORE.health()


def health_dict() -> dict[str, Any]:
    """:func:`health` as JSON for the dashboard state payload."""
    return asdict(_STORE.health())


@_noop_on_empty(None)
@_resilient
def insert_spans(spans: list[dict[str, Any]]) -> None:
    """Upsert decoded spans (see groom.otlp.parse_traces)."""
    if not spans:
        return
    with _STORE.writing() as conn:
        promoted = ", ".join(_SPAN_VALUE_COLUMNS)
        placeholders = ", ".join("?" * len(_SPAN_VALUE_COLUMNS))
        conn.executemany(
            "INSERT OR REPLACE INTO spans (span_id, trace_id, parent_id, run_id, workflow,"
            " repo, branch, node, name, run_dir, start_ts, end_ts, status, attrs_json,"
            f" {promoted})"
            f" VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, {placeholders})",
            [
                (
                    s["span_id"],
                    s["trace_id"],
                    s.get("parent_id", ""),
                    s.get("run_id", ""),
                    s.get("workflow", ""),
                    s.get("repo", ""),
                    s.get("branch", ""),
                    s.get("node", ""),
                    s.get("name", ""),
                    s.get("run_dir", ""),
                    s.get("start_ts", 0.0),
                    s.get("end_ts", 0.0),
                    s.get("status", "UNSET"),
                    json.dumps(s.get("attrs") or {}),
                    *_promoted(s, s.get("attrs") or {}),
                )
                for s in spans
            ],
        )


def insert_metrics(points: list[dict[str, Any]]) -> None:
    """Append decoded metric points (see groom.otlp.parse_metrics)."""
    points = [p for p in points if p.get("name") not in LIVENESS_METRICS]
    if not points:
        return
    _write_metrics(points)


@_resilient
def _write_metrics(points: list[dict[str, Any]]) -> None:
    """Store already-filtered, non-empty metric points."""
    with _STORE.writing() as conn:
        conn.executemany(
            "INSERT INTO metrics (run_id, name, ts, value, attrs_json) VALUES (?, ?, ?, ?, ?)",
            [
                (
                    p.get("run_id", ""),
                    p["name"],
                    p.get("ts", 0.0),
                    float(p.get("value", 0.0)),
                    json.dumps(p.get("attrs") or {}),
                )
                for p in points
            ],
        )


def _log_attribute(attrs: dict[str, Any], key: str) -> str | None:
    """One log snapshot field, or NULL when the producer observed no value."""
    raw = attrs.get(key)
    return raw if isinstance(raw, str) and raw else None


@_noop_on_empty(None)
@_resilient
def insert_logs(records: list[dict[str, Any]]) -> None:
    """Append decoded log records (see groom.otlp.parse_logs)."""
    if not records:
        return
    with _STORE.writing() as conn:
        conn.executemany(
            "INSERT INTO logs (run_id, workflow, run_dir, node, logger, severity, body,"
            " ts, trace_id, attrs_json, head, workspace, vcs, origin, branch, repositories)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    r.get("run_id", ""),
                    r.get("workflow", ""),
                    r.get("run_dir", ""),
                    r.get("node", ""),
                    r.get("logger", ""),
                    r.get("severity", "INFO"),
                    r.get("body", ""),
                    r.get("ts", 0.0),
                    r.get("trace_id", ""),
                    json.dumps(r.get("attrs") or {}),
                    _log_attribute(r.get("attrs") or {}, "git.head")
                    or _log_attribute(r.get("attrs") or {}, "head"),
                    _log_attribute(r.get("attrs") or {}, "workspace.path"),
                    _log_attribute(r.get("attrs") or {}, "workspace.vcs"),
                    _log_attribute(r.get("attrs") or {}, "git.origin"),
                    _log_attribute(r.get("attrs") or {}, "git.branch"),
                    _log_attribute(r.get("attrs") or {}, "workhorse.repositories"),
                )
                for r in records
            ],
        )


_SEVERITY_ORDER = ("FATAL", "ERROR", "WARNING", "INFO", "DEBUG", "TRACE")


@_reading
def query_logs(
    run: str = "",
    node: str = "",
    level: str = "",
    contains: str = "",
    limit: int = 200,
    before_ts: float | None = None,
) -> list[dict[str, Any]]:
    """The log search behind ``groom logs``, newest first."""
    where, params = [], []
    if run:
        where.append("run_id = ?")
        params.append(run)
    if node:
        where.append("node = ?")
        params.append(node)
    if level:
        wanted = level.strip().upper()
        if wanted in _SEVERITY_ORDER:
            keep = _SEVERITY_ORDER[: _SEVERITY_ORDER.index(wanted) + 1]
            where.append(f"severity IN ({','.join('?' * len(keep))})")
            params.extend(keep)
    if contains:
        where.append("body LIKE ?")
        params.append(f"%{contains}%")
    if before_ts is not None:
        where.append("ts < ?")
        params.append(float(before_ts))
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    conn = _read_connection()
    rows = conn.execute(
        f"SELECT run_id, workflow, run_dir, node, logger, severity, body, ts, trace_id,"  # noqa: S608
        f" attrs_json, head, workspace, vcs, origin, branch, repositories"
        f" FROM logs {clause} ORDER BY ts DESC, rowid DESC LIMIT ?",
        (*params, limit),
    ).fetchall()
    return [
        {**dict(row), "attrs": json.loads(row["attrs_json"] or "{}")} for row in rows
    ]


def _promoted_or_attr(column: str, key: str) -> str:
    """The promoted column, falling back to the attribute it was promoted from."""
    return f"COALESCE({column}, json_extract(attrs_json, '$.\"{key}\"'))"


_cost = _promoted_or_attr("total_cost_usd", "total_cost_usd")
_duration = _promoted_or_attr("duration_ms", "duration_ms")
_output = _promoted_or_attr("output_tokens", "usage.output_tokens")
_input = _promoted_or_attr("input_tokens", "usage.input_tokens")
_cache_read = _promoted_or_attr("cache_read_tokens", "usage.cache_read_input_tokens")
_cache_write = _promoted_or_attr(
    "cache_creation_tokens", "usage.cache_creation_input_tokens"
)

_ESTIMABLE = (
    "name = 'agent_turn' AND ("
    f"{_input} IS NOT NULL OR {_output} IS NOT NULL"
    f" OR {_cache_read} IS NOT NULL OR {_cache_write} IS NOT NULL)"
)


@_reading
def unpriced_models(run: str = "") -> dict[str, int]:
    """Models with turns the rate card cannot price, and how many turns each has."""
    clauses = [_ESTIMABLE]
    params: list[Any] = []
    if run:
        clauses.append("run_id = ?")
        params.append(run)
    conn = _read_connection()
    rows = conn.execute(
        "SELECT COALESCE(priced_model, json_extract(attrs_json, '$.model')) AS model,"  # noqa: S608
        f" COUNT(*) AS turns FROM spans WHERE {' AND '.join(clauses)} GROUP BY model",
        params,
    ).fetchall()
    found = Counter[str]()
    for row in rows:
        model = str(row["model"] or "")
        if prices.price_for(model) is None:
            found[model or "(no model recorded)"] += row["turns"]
    return dict(found.most_common())


def reprice(run: str = "", missing_only: bool = True) -> dict[str, Any]:
    """Recompute `est_cost_usd` over turns already in the store."""
    clauses = [_ESTIMABLE]
    params: list[Any] = []
    if run:
        clauses.append("run_id = ?")
        params.append(run)
    if missing_only:
        clauses.append("est_cost_usd IS NULL")
    rows = _estimable_turns(clauses, params)
    updates: list[tuple[float, str, str]] = []
    unpriced: Counter[str] = Counter()
    for row in rows:
        model = str(row["priced_model"] or row["model"] or "")
        estimated = _estimated(model, dict(row))
        if estimated is None:
            unpriced[model or "(no model recorded)"] += 1
            continue
        updates.append((estimated, model, row["span_id"]))
    apply_estimates(updates)
    return {
        "considered": len(rows),
        "priced": len(updates),
        "est_cost_usd": sum(value for value, _model, _span in updates),
        "unpriced": dict(unpriced.most_common()),
    }


@_reading
def _estimable_turns(clauses: list[str], params: list[Any]) -> list[sqlite3.Row]:
    """Turns matching `clauses`, with everything pricing one needs already coalesced."""
    return (
        _read_connection()
        .execute(
            "SELECT span_id, priced_model,"  # noqa: S608
            " json_extract(attrs_json, '$.model') AS model,"
            " json_extract(attrs_json, '$.backend') AS backend,"
            " json_extract(attrs_json, '$.\"session.id\"') AS session_id,"
            f" {_input} AS input_tokens, {_output} AS output_tokens,"
            f" {_cache_read} AS cache_read_tokens, {_cache_write} AS cache_creation_tokens"
            f" FROM spans WHERE {' AND '.join(clauses)}",
            params,
        )
        .fetchall()
    )


@_reading
def unpriceable_turns(run: str = "") -> list[dict[str, Any]]:
    """Turns with tokens, no estimate, and a model no rate covers."""
    clauses = [_ESTIMABLE, "est_cost_usd IS NULL"]
    params: list[Any] = []
    if run:
        clauses.append("run_id = ?")
        params.append(run)
    return [
        dict(row)
        for row in _estimable_turns(clauses, params)
        if prices.price_for(str(row["model"] or "")) is None
    ]


@_resilient
def apply_estimates(updates: list[tuple[float, str, str]]) -> int:
    """Write `(est_cost_usd, priced_model, span_id)` triples; rows touched."""
    with _STORE.writing() as conn:
        conn.executemany(
            "UPDATE spans SET est_cost_usd = ?, priced_model = ? WHERE span_id = ?",
            updates,
        )
    return len(updates)


@_reading
def node_costs(run: str = "", limit: int = 100) -> list[dict[str, Any]]:
    """Per-node agent spend for a run: where the money and the rework went."""
    clauses, params = ["name = 'agent_turn'"], []
    if run:
        clauses.append("run_id = ?")
        params.append(run)
    conn = _read_connection()
    rows = conn.execute(
        "SELECT node,"  # noqa: S608 — clauses are literals; every value is bound
        " COUNT(*) AS turns,"
        " COUNT(DISTINCT json_extract(attrs_json, '$.work_id')) AS work_items,"
        f" SUM({_cost} IS NOT NULL) AS cost_turns,"
        f" SUM({_cost} = 0 AND COALESCE({_output}, 0) > 0) AS zero_cost_turns,"
        " GROUP_CONCAT(DISTINCT json_extract(attrs_json, '$.backend')) AS backends,"
        f" SUM({_cost}) AS cost_usd,"
        " SUM(est_cost_usd) AS est_cost_usd,"
        " SUM(est_cost_usd IS NOT NULL) AS est_turns,"
        f" SUM({_duration}) / 60000.0 AS minutes,"
        f" SUM({_output}) AS output_tokens"
        f" FROM spans WHERE {' AND '.join(clauses)}"
        " GROUP BY node ORDER BY cost_usd DESC NULLS LAST, minutes DESC LIMIT ?",
        (*params, max(1, min(int(limit), 1000))),
    ).fetchall()
    total = sum(row["cost_usd"] or 0.0 for row in rows)
    return [
        {
            **dict(row),
            "share": (row["cost_usd"] or 0.0) / total if total else 0.0,
            "turns_per_work_id": (
                row["turns"] / row["work_items"] if row["work_items"] else None
            ),
        }
        for row in rows
    ]


_LOOP_VERDICTS = (
    (0.8, "converged"),
    (0.5, "loose"),
    (0.3, "churning"),
    (0.0, "thrashing"),
)

MIN_LOOP_WORK_ITEMS = 3


@dataclass(frozen=True, slots=True)
class Lap:
    """One turn of a loop, as the three numbers ranking it needs."""

    cost: float | None
    suspect_zero: bool
    est: float | None


@_reading
def loop_convergence(
    run: str = "",
    workflow: str = "",
    min_work_items: int = MIN_LOOP_WORK_ITEMS,
    since_ts: float | None = None,
) -> list[dict[str, Any]]:
    """Per-node lap distributions: which review→rework loops converge, and what the ones that don't are costing."""
    clauses = [
        "name = 'agent_turn'",
        "json_extract(attrs_json, '$.work_id') IS NOT NULL",
    ]
    params: list[Any] = []
    if run:
        clauses.append("run_id = ?")
        params.append(run)
    if workflow:
        clauses.append("workflow = ?")
        params.append(workflow)
    if since_ts is not None:
        clauses.append("start_ts >= ?")
        params.append(float(since_ts))
    rows = (
        _read_connection()
        .execute(
            "SELECT node, run_id,"  # noqa: S608 — clauses are literals; every value is bound
            " json_extract(attrs_json, '$.work_id') AS work_id,"
            f" {_cost} AS cost_usd, {_cost} = 0 AND COALESCE({_output}, 0) > 0 AS suspect_zero,"
            " est_cost_usd, start_ts"
            f" FROM spans WHERE {' AND '.join(clauses)} ORDER BY start_ts, end_ts, rowid",
            params,
        )
        .fetchall()
    )

    laps: dict[str, dict[tuple[str, str], list[Lap]]] = {}
    for row in rows:
        item = (row["run_id"], str(row["work_id"]))
        lap = Lap(row["cost_usd"], bool(row["suspect_zero"]), row["est_cost_usd"])
        laps.setdefault(row["node"], {}).setdefault(item, []).append(lap)

    report = [_loop_row(node, items) for node, items in laps.items()]
    report = [row for row in report if row["work_items"] >= min_work_items]
    report.sort(
        key=lambda row: (-(row["excess_cost_usd"] or 0.0), -row["excess_turns"])
    )
    return report


def _loop_row(node: str, items: dict[tuple[str, str], list[Lap]]) -> dict[str, Any]:
    counts = sorted(len(laps) for laps in items.values())
    turns, work_items = sum(counts), len(counts)
    exit_rate = work_items / turns
    peak = counts[-1]
    every = [lap for laps in items.values() for lap in laps]
    priced = [lap.cost for lap in every if lap.cost is not None]
    estimated = [lap.est for lap in every if lap.est is not None]
    excess = [
        lap.cost for laps in items.values() for lap in laps[1:] if lap.cost is not None
    ]
    excess_est = [
        lap.est for laps in items.values() for lap in laps[1:] if lap.est is not None
    ]
    return {
        "node": node,
        "work_items": work_items,
        "turns": turns,
        "priced_turns": len(priced),
        "est_turns": len(estimated),
        "zero_cost_turns": sum(1 for lap in every if lap.suspect_zero),
        "excess_turns": turns - work_items,
        "exit_rate": exit_rate,
        "mean_laps": turns / work_items,
        "median_laps": counts[work_items // 2],
        "max_laps": peak,
        "at_max": sum(1 for count in counts if count == peak),
        "share_ge3": sum(1 for count in counts if count >= 3) / work_items,
        "cost_usd": sum(priced) if priced else None,
        "est_cost_usd": sum(estimated) if estimated else None,
        "excess_cost_usd": sum(excess) if excess else None,
        "excess_est_cost_usd": sum(excess_est) if excess_est else None,
        "verdict": next(name for floor, name in _LOOP_VERDICTS if exit_rate >= floor),
    }


_VERDICT_SUFFIXES = ("_verdict", "_disposition", "_failure_class", "_refutation_class")


def _profile_turn_summary(turns: list[dict[str, Any]]) -> dict[str, Any]:
    work_items = {
        str(value)
        for turn in turns
        if (value := turn["attrs"].get("work_id") or turn["attrs"].get("wf.work_id"))
    }
    visits = len(
        {(turn["trace_id"], turn["parent_id"] or turn["span_id"]) for turn in turns}
    )
    costs = [
        float(turn["profile_cost_usd"])
        for turn in turns
        if turn["profile_cost_usd"] is not None
    ]
    zeroed = sum(
        turn["profile_cost_usd"] == 0 and (turn["profile_output_tokens"] or 0) > 0
        for turn in turns
    )
    seconds = sum(max(0.0, turn["end_ts"] - turn["start_ts"]) for turn in turns)
    return {
        "turns": len(turns),
        "visits": visits,
        "backend_retries": len(turns) - visits,
        "work_items": len(work_items),
        "turns_per_work": len(turns) / len(work_items) if work_items else None,
        "visits_per_work": visits / len(work_items) if work_items else None,
        "agent_s": seconds,
        "cost_usd": sum(costs) if costs else None,
        "cost_turns": len(costs),
        "missing_cost_turns": len(turns) - len(costs),
        "cost_coverage": len(costs) / len(turns) if turns else None,
        "zero_cost_output_turns": zeroed,
        "output_tokens": sum(turn["profile_output_tokens"] or 0 for turn in turns),
        "backends": sorted(
            {
                str(turn["attrs"].get("backend"))
                for turn in turns
                if turn["attrs"].get("backend")
            }
        ),
    }


def _profile_groups(
    turns: list[dict[str, Any]], *, verdicts: bool
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for turn in turns:
        for dimension, raw in turn["attrs"].items():
            if not isinstance(raw, str) or not raw:
                continue
            is_verdict = dimension.endswith(_VERDICT_SUFFIXES)
            is_attempt = (
                "." in dimension
                and raw.isdigit()
                and str(int(raw)) == raw
                and not dimension.startswith("workhorse.")
            )
            if (verdicts and is_verdict) or (not verdicts and is_attempt):
                grouped[(dimension, raw, turn["node"])].append(turn)

    rows = []
    for (dimension, value, node), members in grouped.items():
        rows.append(
            {
                "dimension": dimension,
                "value": value,
                "node": node,
                **_profile_turn_summary(members),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row["dimension"],
            int(row["value"]) if not verdicts else row["value"],
            row["node"],
        ),
    )


def _profile_verdict_decisions(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """How many times each gate actually reached each verdict, cost aside."""
    current: dict[tuple[str, str], str] = {}
    counts: Counter[tuple[str, str]] = Counter()
    for span in spans:
        trace = span["trace_id"]
        present = {
            dimension: raw
            for dimension, raw in span["attrs"].items()
            if isinstance(raw, str) and raw and dimension.endswith(_VERDICT_SUFFIXES)
        }
        for dimension, raw in present.items():
            if current.get((trace, dimension)) != raw:
                counts[(dimension, raw)] += 1
                current[(trace, dimension)] = raw
        for key in [
            key for key in current if key[0] == trace and key[1] not in present
        ]:
            del current[key]
    return [
        {"dimension": dimension, "value": value, "decisions": count}
        for (dimension, value), count in sorted(counts.items())
    ]


def _span_category(span: dict[str, Any], parent_keys: set[tuple[str, str]]) -> str:
    attrs = span["attrs"]
    kind = str(attrs.get("workhorse.span_kind") or "")
    if kind == "wait":
        return f"wait:{attrs.get('workhorse.wait_kind') or 'unknown'}"
    if span["name"] == "agent_turn":
        return "agent"
    if kind == "infra":
        return "infra"
    has_child = (span["trace_id"], span["span_id"]) in parent_keys
    if not has_child and not kind and not span["name"].startswith("run:"):
        return "deterministic"
    return ""


def _resume_intervals(spans: list[dict[str, Any]]) -> list[tuple[float, float]]:
    sessions: dict[str, dict[str, Any]] = {}
    for span in spans:
        trace = span["trace_id"]
        session = sessions.setdefault(
            trace,
            {"start": span["start_ts"], "end": span["end_ts"], "generation": None},
        )
        session["start"] = min(session["start"], span["start_ts"])
        session["end"] = max(session["end"], span["end_ts"])
        generation = span.get("resume_generation")
        if isinstance(generation, int) and generation > 0:
            session["generation"] = generation

    ordered = sorted(sessions.values(), key=lambda session: session["start"])
    gaps = []
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if (
            current["start"] > previous["end"]
            and previous["generation"] is not None
            and current["generation"] is not None
            and previous["generation"] != current["generation"]
        ):
            gaps.append((previous["end"], current["start"]))
    return gaps


def _profile_time_partition(
    spans: list[dict[str, Any]], start_ts: float, end_ts: float
) -> dict[str, Any]:
    events: dict[float, list[tuple[str, int]]] = defaultdict(list)
    parent_keys = {
        (span["trace_id"], span["parent_id"]) for span in spans if span["parent_id"]
    }
    for span in spans:
        category = _span_category(span, parent_keys)
        if category and span["end_ts"] > span["start_ts"]:
            events[span["start_ts"]].append((category, 1))
            events[span["end_ts"]].append((category, -1))
    for gap_start, gap_end in _resume_intervals(spans):
        events[gap_start].append(("resume_gap", 1))
        events[gap_end].append(("resume_gap", -1))

    points = sorted({start_ts, end_ts, *events})
    active: Counter[str] = Counter()
    totals: defaultdict[str, float] = defaultdict(float)
    waits: defaultdict[str, float] = defaultdict(float)
    for left, right in zip(points, points[1:], strict=False):
        for category, delta in events.get(left, []):
            active[category] += delta
        duration = max(0.0, right - left)
        wait_kinds = sorted(
            category.removeprefix("wait:")
            for category, count in active.items()
            if category.startswith("wait:") and count > 0
        )
        if active["resume_gap"] > 0:
            totals["resume_gap"] += duration
        elif wait_kinds:
            kind = wait_kinds[0] if len(wait_kinds) == 1 else "overlap"
            totals["wait"] += duration
            waits[kind] += duration
        elif active["agent"] > 0:
            totals["agent"] += duration
        elif active["infra"] > 0:
            totals["infra"] += duration
        elif active["deterministic"] > 0:
            totals["deterministic"] += duration
        else:
            totals["unclassified"] += duration

    wall = max(0.0, end_ts - start_ts)
    return {
        "wall": wall,
        "agent": totals["agent"],
        "deterministic": totals["deterministic"],
        "infra": totals["infra"],
        "wait": totals["wait"],
        "waits_by_kind": dict(sorted(waits.items())),
        "resume_gap": totals["resume_gap"],
        "unclassified": totals["unclassified"],
    }


@_reading
def run_profile(run: str) -> dict[str, Any] | None:
    """Partition one run's retained wall time and aggregate its agent rework."""
    if not run:
        return None
    rows = (
        _read_connection()
        .execute(
            f"SELECT {_SPAN_COLUMNS}, duration_ms AS profile_duration_ms,"  # noqa: S608
            f" {_cost} AS profile_cost_usd, {_output} AS profile_output_tokens,"
            " resume_generation FROM spans WHERE run_id = ? ORDER BY start_ts",
            (run,),
        )
        .fetchall()
    )
    spans = [
        {**dict(row), "attrs": json.loads(row["attrs_json"] or "{}")} for row in rows
    ]
    metric_bounds = (
        _read_connection()
        .execute(
            "SELECT MIN(ts) AS first_ts, MAX(ts) AS last_ts FROM metrics WHERE run_id = ?",
            (run,),
        )
        .fetchone()
    )
    metric_start = metric_bounds["first_ts"] if metric_bounds else None
    metric_end = metric_bounds["last_ts"] if metric_bounds else None
    if not spans and metric_start is None:
        return None

    starts = [span["start_ts"] for span in spans]
    ends = [span["end_ts"] for span in spans]
    if metric_start is not None:
        starts.append(metric_start)
        ends.append(metric_end)
    start_ts, end_ts = min(starts), max(ends)
    turns = [span for span in spans if span["name"] == "agent_turn"]
    return {
        "run_id": run,
        "workflow": next((span["workflow"] for span in spans if span["workflow"]), ""),
        "observed_start_ts": start_ts,
        "observed_end_ts": end_ts,
        "time_s": _profile_time_partition(spans, start_ts, end_ts),
        "work": _profile_turn_summary(turns),
        "attempt_groups": _profile_groups(turns, verdicts=False),
        "verdict_groups": _profile_groups(turns, verdicts=True),
        "verdict_decisions": _profile_verdict_decisions(spans),
    }


_SPAN_COLUMNS = (
    "span_id, trace_id, parent_id, run_id, workflow, repo, branch, node, name,"
    " run_dir, start_ts, end_ts, status, attrs_json, head_start, head_end,"
    " workspace_start, workspace_end, vcs_start, vcs_end, origin_start, origin_end,"
    " branch_start, branch_end, repositories_start, repositories_end"
)


@_reading
def query_spans(
    run: str = "",
    node: str = "",
    status: str = "",
    slower_than: float | None = None,
    limit: int = 200,
    before_ts: float | None = None,
    since_ts: float | None = None,
) -> list[dict[str, Any]]:
    """The /traces search: filter the spans table, newest first."""
    clauses, params = ["1=1"], []
    if run:
        clauses.append("run_id = ?")
        params.append(run)
    if node:
        clauses.append("node = ?")
        params.append(node)
    if status:
        clauses.append("status = ?")
        params.append(status.upper())
    if slower_than is not None:
        clauses.append("(end_ts - start_ts) >= ?")
        params.append(float(slower_than))
    if before_ts is not None:
        clauses.append("start_ts < ?")
        params.append(float(before_ts))
    if since_ts is not None:
        clauses.append("start_ts >= ?")
        params.append(float(since_ts))
    params.append(max(1, min(int(limit), 1000)))
    rows = (
        _read_connection()
        .execute(
            f"SELECT {_SPAN_COLUMNS} FROM spans WHERE {' AND '.join(clauses)}"  # noqa: S608 - literals
            " ORDER BY start_ts DESC LIMIT ?",
            params,
        )
        .fetchall()
    )
    return [dict(row) for row in rows]


@_reading
def detail_metrics(run: str, limit: int = 60) -> list[dict[str, Any]]:
    """Recent persisted metrics for a pane's initial history snapshot."""
    rows = _read_connection().execute(
        "SELECT name, ts, value, attrs_json FROM metrics"
        " WHERE run_id = ? ORDER BY ts DESC, rowid DESC LIMIT ?",
        (run, limit),
    ).fetchall()
    return [
        {"name": row["name"], "ts": row["ts"], "value": row["value"],
         "attrs": json.loads(row["attrs_json"])}
        for row in rows
    ]


@_reading
def detail_spans(run: str) -> list[dict[str, Any]]:
    """Compact span identities for an open pane's snapshot and idempotent updates."""
    rows = _read_connection().execute(
        "SELECT span_id, node, name, start_ts, end_ts, status FROM spans"
        " WHERE run_id = ?",
        (run,),
    ).fetchall()
    return [dict(row) for row in rows]


@_reading
def run_summaries(
    limit: int = 50, now: float | None = None, run: str = ""
) -> list[dict[str, Any]]:
    """One row per run for the fleet/telemetry view: workflow, span window, and span/error counts."""
    cutoff = (now if now is not None else time.time()) - ACTIVE_WINDOW_S
    params: list[Any] = [cutoff]
    run_clause = ""
    if run:
        run_clause = "AND run_id = ?"
        params.append(run)
    params.append(max(1, min(int(limit), 500)))
    rows = (
        _read_connection()
        .execute(
            "SELECT run_id, MAX(workflow) AS workflow, MAX(repo) AS repo,"
            " MIN(start_ts) AS first_ts, MAX(end_ts) AS last_ts,"
            " COUNT(*) AS span_count,"
            " SUM(CASE WHEN status = 'ERROR' THEN 1 ELSE 0 END) AS error_count"
            f" FROM spans WHERE run_id != '' AND end_ts >= ? {run_clause} GROUP BY run_id"  # noqa: S608 - literal clause, bound values
            " ORDER BY last_ts DESC LIMIT ?",
            params,
        )
        .fetchall()
    )
    return [dict(row) for row in rows]


LIVE_AFTER_S = float(os.environ.get("GROOM_LIVE_AFTER_S", "180"))


_TEST_RUN_DIR_MARKERS = ("/pytest-of-", "/.workhorse-test/", "/.groom-test/")

_PY_TEMP_DIR = re.compile(r"^tmp[A-Za-z0-9_]{6,}$")


def _temp_roots() -> tuple[str, ...]:
    """Temp-dir prefixes a throwaway run dir sits under."""
    roots = {tempfile.gettempdir().rstrip("/"), "/tmp"}
    return tuple(f"{root}/" for root in sorted(roots) if root)


def is_test_run_dir(run_dir: str) -> bool:
    """Did this run dir certainly come from a test process?"""
    if not run_dir:
        return False
    return any(marker in run_dir for marker in _TEST_RUN_DIR_MARKERS)


def is_scratch_run_dir(run_dir: str) -> bool:
    """Does this run dir look throwaway — a certain test dir, or a Python temp one?"""
    if is_test_run_dir(run_dir):
        return True
    for root in _temp_roots():
        if run_dir.startswith(root):
            return bool(_PY_TEMP_DIR.match(run_dir[len(root) :].split("/", 1)[0]))
    return False


@_reading
def _test_run_ids() -> set[str]:
    """The run ids whose run dir says they were throwaway (:func:`is_scratch_run_dir`)."""
    conn = _read_connection()
    pairs: set[tuple[str, str]] = set()
    for table in ("spans", "logs"):
        pairs.update(
            (row["run_id"], row["run_dir"])
            for row in conn.execute(
                f"SELECT DISTINCT run_id, run_dir FROM {table} WHERE run_dir != ''"  # noqa: S608 - literal table name
            )
        )
    return {
        run_id for run_id, run_dir in pairs if run_id and is_scratch_run_dir(run_dir)
    }


@_reading
def test_run_ids() -> set[str]:
    """:func:`_test_run_ids`, with the store's heal-and-retry around it."""
    return _test_run_ids()


_PURGE_CHUNK = 500


@_resilient
def purge_test_runs(dry_run: bool = False, vacuum: bool = True) -> dict[str, int]:
    """Delete every span/metric/log belonging to a test run."""
    run_ids = sorted(_test_run_ids())
    counts = {"runs": len(run_ids), "spans": 0, "metrics": 0, "logs": 0, "turns": 0}

    def sweep(conn: sqlite3.Connection) -> None:
        for start in range(0, len(run_ids), _PURGE_CHUNK):
            chunk = run_ids[start : start + _PURGE_CHUNK]
            marks = ",".join("?" * len(chunk))
            for table in ("spans", "metrics", "logs", "turns"):
                verb = "SELECT COUNT(*) AS n FROM" if dry_run else "DELETE FROM"
                cursor = conn.execute(
                    f"{verb} {table} WHERE run_id IN ({marks})", chunk
                )  # noqa: S608 - literal table name, bound values
                counts[table] += cursor.fetchone()["n"] if dry_run else cursor.rowcount

    if dry_run:
        sweep(_connection())
        return counts
    with _STORE.writing() as conn:
        sweep(conn)
    if vacuum and counts["runs"]:
        with _STORE.lock:
            _connection().execute("VACUUM")
    return counts


@_noop_on_empty(0)
@_resilient
def insert_turns(rows: list[dict[str, Any]]) -> int:
    """Index archived turn records; how many rows the index gained or replaced."""
    if not rows:
        return 0
    with _STORE.writing() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO turns (run_id, workflow, flow, node, session_id,"
            " generation, seq, ts, backend, source, path, bytes, sha256, head)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    r.get("run_id", ""),
                    r.get("workflow", ""),
                    r.get("flow", ""),
                    r.get("node", ""),
                    r.get("session_id", ""),
                    r.get("generation"),
                    r.get("seq"),
                    float(r.get("ts") or 0.0),
                    r.get("backend", ""),
                    r.get("source", ""),
                    r.get("path", ""),
                    int(r.get("bytes") or 0),
                    r.get("sha256", ""),
                    r.get("head") or None,
                )
                for r in rows
            ],
        )
    return len(rows)


@_reading
def query_turns(
    run: str = "",
    node: str = "",
    session: str = "",
    workflow: str = "",
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Archived turns, newest visit last — a node's laps read top to bottom."""
    clauses: list[str] = []
    params: list[Any] = []
    for column, value in (
        ("run_id", run),
        ("node", node),
        ("session_id", session),
        ("workflow", workflow),
    ):
        if value:
            clauses.append(f"{column} = ?")
            params.append(value)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(max(1, limit))
    rows = _read_connection().execute(
        "SELECT run_id, workflow, flow, node, session_id, generation, seq, ts, backend,"
        f" source, path, bytes, sha256, head FROM turns {where}"  # noqa: S608 - bound values
        " ORDER BY run_id, generation, seq LIMIT ?",
        params,
    )
    return [dict(row) for row in rows]


@_reading
def run_directories() -> list[dict[str, Any]]:
    """Every run telemetry has seen a directory for: run_id, run_dir, workflow."""
    return [
        dict(row)
        for row in _read_connection().execute(
            "SELECT DISTINCT run_id, run_dir, workflow FROM spans"
            " WHERE run_dir != '' AND run_id != ''"
        )
    ]


_PRUNE_CHUNK = 50_000

_NEVER_ARCHIVED_METRICS = UNARCHIVED_DELETABLE_METRICS + LIVENESS_METRICS


@_resilient
def _delete_chunk(table: str, clause: str, params: tuple[Any, ...]) -> int:
    """One ``_PRUNE_CHUNK``-row DELETE, in its own transaction; rows removed."""
    with _STORE.writing() as conn:
        return conn.execute(
            f"DELETE FROM {table} WHERE rowid IN"  # noqa: S608 - literal table/clause, bound values
            f" (SELECT rowid FROM {table} WHERE {clause} LIMIT ?)",
            (*params, _PRUNE_CHUNK),
        ).rowcount


def _chunked_delete(table: str, clause: str, params: tuple[Any, ...]) -> int:
    """``DELETE FROM <table> WHERE <clause>``, ``_PRUNE_CHUNK`` rows per transaction."""
    removed = 0
    while True:
        count = _delete_chunk(table, clause, params)
        removed += count
        if count < _PRUNE_CHUNK:
            return removed


@_reading
def _expired_run_ids(cutoff: float) -> set[str]:
    """Run ids still holding at least one row older than ``cutoff``."""
    conn = _read_connection()
    found: set[str] = set()
    for sql in (
        "SELECT DISTINCT run_id FROM spans WHERE end_ts < ?",
        "SELECT DISTINCT run_id FROM logs WHERE ts < ?",
        "SELECT DISTINCT run_id FROM metrics WHERE ts < ?",
    ):
        found.update(row["run_id"] for row in conn.execute(sql, (cutoff,)))
    return found


def prune(
    retention_days: float = RETENTION_DAYS,
    now: float | None = None,
    archived: set[str] | None = None,
) -> int:
    """Drop expired telemetry for runs that are safe to drop; rows removed."""
    stamp = now if now is not None else time.time()
    cutoff = stamp - retention_days * 86400
    removed = 0

    placeholders = ",".join("?" * len(_NEVER_ARCHIVED_METRICS))
    removed += _chunked_delete(
        "metrics",
        f"ts < ? AND name IN ({placeholders})",
        (cutoff, *_NEVER_ARCHIVED_METRICS),
    )

    expired = _expired_run_ids(cutoff)
    deletable = (set(archived) if archived else set()) | {""}
    if expired:
        deletable |= _test_run_ids()
    for run_id in sorted(deletable & expired):
        removed += _chunked_delete(
            "spans", "run_id = ? AND end_ts < ?", (run_id, cutoff)
        )
        removed += _chunked_delete("logs", "run_id = ? AND ts < ?", (run_id, cutoff))
        removed += _chunked_delete("metrics", "run_id = ? AND ts < ?", (run_id, cutoff))

    _checkpoint()
    _STORE.note_prune()
    return removed


@dataclass(frozen=True, slots=True)
class RecentRun:
    """One row of :func:`recent_runs` — what ``groom recent`` shows."""

    run_id: str
    workflow: str = ""
    max_ts: float = 0.0
    spans: int = 0


@dataclass(frozen=True)
class RunBounds:
    """What :mod:`groom.archive` needs to decide a run is done and name its file."""

    run_id: str
    workflow: str = ""
    repo: str = ""
    branch: str = ""
    run_dir: str = ""
    min_ts: float = 0.0
    max_ts: float = 0.0
    spans: int = 0
    logs: int = 0
    metrics: int = 0

    @property
    def rows(self) -> int:
        return self.spans + self.logs + self.metrics


@_reading
def run_bounds() -> dict[str, RunBounds]:
    """Per-run timestamp bounds, archivable row counts and identity."""
    conn = _read_connection()
    span: dict[str, tuple[float, float, int]] = {}
    log: dict[str, tuple[float, float, int]] = {}
    metric: dict[str, tuple[float, float, int]] = {}
    identity: dict[str, tuple[str, str, str, str]] = {}

    for row in conn.execute(
        "SELECT run_id, MIN(start_ts) AS lo, MAX(MAX(start_ts, end_ts)) AS hi,"
        " COUNT(*) AS n FROM spans WHERE run_id != '' GROUP BY run_id"
    ):
        span[row["run_id"]] = (row["lo"] or 0.0, row["hi"] or 0.0, row["n"])
    for row in conn.execute(
        "SELECT run_id, MIN(ts) AS lo, MAX(ts) AS hi, COUNT(*) AS n"
        " FROM logs WHERE run_id != '' GROUP BY run_id"
    ):
        log[row["run_id"]] = (row["lo"] or 0.0, row["hi"] or 0.0, row["n"])
    kept = ",".join("?" * len(ARCHIVED_METRICS))
    for row in conn.execute(
        "SELECT run_id, MIN(ts) AS lo, MAX(ts) AS hi,"
        f" SUM(CASE WHEN name IN ({kept}) THEN 1 ELSE 0 END) AS n"  # noqa: S608 - bound placeholders
        " FROM metrics WHERE run_id != '' GROUP BY run_id",
        ARCHIVED_METRICS,
    ):
        metric[row["run_id"]] = (row["lo"] or 0.0, row["hi"] or 0.0, row["n"] or 0)
    for row in conn.execute(
        "SELECT run_id, workflow, repo, branch, run_dir, MAX(start_ts)"
        " FROM spans WHERE run_id != '' GROUP BY run_id"
    ):
        identity[row["run_id"]] = (
            row["workflow"] or "",
            row["repo"] or "",
            row["branch"] or "",
            row["run_dir"] or "",
        )

    bounds: dict[str, RunBounds] = {}
    for run_id in set(span) | set(log) | set(metric):
        parts = [
            part
            for part in (span.get(run_id), log.get(run_id), metric.get(run_id))
            if part
        ]
        stamps = [value for lo, hi, _ in parts for value in (lo, hi) if value]
        workflow, repo, branch, run_dir = identity.get(run_id, ("", "", "", ""))
        bounds[run_id] = RunBounds(
            run_id=run_id,
            workflow=workflow,
            repo=repo,
            branch=branch,
            run_dir=run_dir,
            min_ts=min(stamps) if stamps else 0.0,
            max_ts=max(stamps) if stamps else 0.0,
            spans=span.get(run_id, (0.0, 0.0, 0))[2],
            logs=log.get(run_id, (0.0, 0.0, 0))[2],
            metrics=metric.get(run_id, (0.0, 0.0, 0))[2],
        )
    return bounds


@_reading
def recent_runs(limit: int = 10, workflow: str = "") -> list[RecentRun]:
    """Top runs ordered by most-recent activity, alive or dead."""
    conn = _read_connection()

    sql_spans = (
        "SELECT run_id, MAX(MAX(start_ts, end_ts)) AS max_ts,"
        " MAX(workflow) AS workflow, COUNT(*) AS spans"
        " FROM spans WHERE run_id != ''"
    )
    params: tuple = ()
    if workflow:
        sql_spans += " AND workflow = ?"
        params = (workflow,)
    sql_spans += " GROUP BY run_id ORDER BY max_ts DESC"
    if limit > 0:
        sql_spans += " LIMIT ?"
        params_spans = params + (
            limit * 4,
        )
    else:
        params_spans = params
    spans_rows = (
        conn.execute(sql_spans, params_spans)
        if params_spans
        else conn.execute(sql_spans)  # noqa: S608 - bound placeholders
    )

    spans_by_id: dict[str, tuple[float, str, int]] = {}
    for row in spans_rows:
        spans_by_id[row["run_id"]] = (
            float(row["max_ts"] or 0.0),
            row["workflow"] or "",
            int(row["spans"] or 0),
        )
    if not spans_by_id:
        return []

    placeholders = ",".join("?" * len(spans_by_id))
    metrics_rows = conn.execute(
        f"SELECT run_id, MAX(ts) AS max_ts FROM metrics"  # noqa: S608 - bound placeholders
        f" WHERE run_id IN ({placeholders}) GROUP BY run_id",
        tuple(spans_by_id),
    )
    metrics_by_id = {row["run_id"]: float(row["max_ts"] or 0.0) for row in metrics_rows}

    out: list[RecentRun] = []
    for run_id, (span_max_ts, workflow_value, span_count) in spans_by_id.items():
        metric_max_ts = metrics_by_id.get(run_id, 0.0)
        merged_max_ts = max(span_max_ts, metric_max_ts)
        out.append(
            RecentRun(
                run_id=run_id,
                workflow=workflow_value,
                max_ts=merged_max_ts,
                spans=span_count,
            )
        )
    out.sort(key=lambda row: row.max_ts, reverse=True)
    if limit > 0:
        out = out[:limit]
    return out


@_reading
def unarchived_row_counts() -> dict[str, int]:
    """What is in the store that :func:`prune` may delete with no archive behind it."""
    conn = _read_connection()
    placeholders = ",".join("?" * len(_NEVER_ARCHIVED_METRICS))
    counts = {
        "never_archived_metrics": conn.execute(
            f"SELECT COUNT(*) FROM metrics WHERE name IN ({placeholders})",  # noqa: S608 - bound placeholders
            _NEVER_ARCHIVED_METRICS,
        ).fetchone()[0],
        "scratch_runs": len(_test_run_ids()),
    }
    for table in ("spans", "logs", "metrics"):
        counts[f"no_run_id_{table}"] = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE run_id = ''"  # noqa: S608 - literal table name
        ).fetchone()[0]
    return counts


_ARCHIVE_PAGE = 5_000

_ARCHIVE_STREAMS: dict[str, tuple[str, str]] = {
    "span": ("spans", "start_ts"),
    "log": ("logs", "ts"),
    "metric": ("metrics", "ts"),
}


@_reading
def archive_page(
    run_id: str,
    kind: str,
    after: tuple[float, int] = (0.0, 0),
    limit: int = _ARCHIVE_PAGE,
) -> list[dict[str, Any]]:
    """One page of a run's archivable rows, keyset-paginated after ``(ts, rowid)``."""
    table, ts_col = _ARCHIVE_STREAMS[kind]
    clause = ""
    params: list[Any] = [run_id]
    if kind == "metric":
        clause = f" AND name IN ({','.join('?' * len(ARCHIVED_METRICS))})"
        params.extend(ARCHIVED_METRICS)
    stamp, rowid = after
    params.extend((stamp, stamp, rowid, limit))
    rows = _read_connection().execute(
        f"SELECT rowid AS _rowid, {ts_col} AS _ts, * FROM {table}"  # noqa: S608 - literal table/column
        f" WHERE run_id = ?{clause} AND ({ts_col} > ? OR ({ts_col} = ? AND rowid > ?))"
        f" ORDER BY {ts_col}, rowid LIMIT ?",
        params,
    )
    return [dict(row) for row in rows]


def delete_run_telemetry(run_id: str) -> int:
    """Drop every span, log and metric belonging to ``run_id``; rows removed."""
    if not run_id:
        return 0
    removed = 0
    for table in ("spans", "logs", "metrics"):
        removed += _chunked_delete(table, "run_id = ?", (run_id,))
    return removed


def _checkpoint() -> None:
    """Fold the write-ahead log back into the database file, and truncate it."""
    try:
        with _STORE.lock:
            row = _connection().execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    except sqlite3.Error as exc:
        logger.warning("groom: WAL checkpoint declined: %s", exc)
        return
    busy = int(row[0]) if row else 0
    _STORE.note_checkpoint(busy)
    if busy:
        logger.info(
            "groom: WAL checkpoint found a reader in the way; %s frames left in place",
            row[1] if row else "?",
        )


@_resilient
def checkpoint() -> None:
    """:func:`_checkpoint`, healing the connection if the PRAGMA itself cannot run."""
    _checkpoint()



ATTEND_RUNNING, ATTEND_COMPLETED = "running", "completed"


def _attend_row(row: sqlite3.Row) -> dict[str, Any]:
    """A row with ``session_ids`` back as the ordered list it is stored as JSON for."""
    record = dict(row)
    raw = record.get("session_ids") or ""
    try:
        parsed = json.loads(raw) if raw else []
    except ValueError:
        parsed = []
    record["session_ids"] = (
        [str(item) for item in parsed] if isinstance(parsed, list) else []
    )
    return record


@_resilient
def attend_start(
    job_id: str,
    *,
    run_id: str = "",
    workflow: str = "",
    run_dir: str = "",
    workspace: str = "",
    kind: str = "",
    reason: str = "",
    node: str = "",
    gate_path: str = "",
    session_id: str = "",
    pid: int | None = None,
    started_at: float | None = None,
) -> None:
    """Record a dispatch as ``running``, before the attendant's first byte of output."""
    with _STORE.writing() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO attend_sessions (job_id, run_id, workflow, run_dir,"
            " workspace, kind, reason, node, gate_path, status, session_ids, pid,"
            " exit_code, started_at, ended_at, released_state)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL, '')",
            (
                job_id,
                run_id,
                workflow,
                run_dir,
                workspace,
                kind,
                reason,
                node,
                gate_path,
                ATTEND_RUNNING,
                json.dumps([session_id] if session_id else []),
                pid,
                float(started_at if started_at is not None else time.time()),
            ),
        )


@_resilient
def attend_append_session(job_id: str, session_id: str, pid: int | None = None) -> None:
    """Re-arm an existing row with a fresh session and pid, keeping its history."""
    with _STORE.writing() as conn:
        row = conn.execute(
            "SELECT session_ids FROM attend_sessions WHERE job_id = ?", (job_id,)
        ).fetchone()
        if row is None:
            return
        try:
            existing = json.loads(row["session_ids"] or "[]")
        except ValueError:
            existing = []
        if not isinstance(existing, list):
            existing = []
        if session_id:
            existing.append(session_id)
        conn.execute(
            "UPDATE attend_sessions SET session_ids = ?, pid = ?, status = ?,"
            " exit_code = NULL, ended_at = NULL WHERE job_id = ?",
            (json.dumps(existing), pid, ATTEND_RUNNING, job_id),
        )


@_resilient
def attend_finish(
    job_id: str,
    *,
    exit_code: int | None = None,
    released_state: str = "",
    ended_at: float | None = None,
) -> None:
    """Flip a row to ``completed``."""
    with _STORE.writing() as conn:
        conn.execute(
            "UPDATE attend_sessions SET status = ?, exit_code = ?, ended_at = ?,"
            " released_state = ? WHERE job_id = ?",
            (
                ATTEND_COMPLETED,
                exit_code,
                float(ended_at if ended_at is not None else time.time()),
                released_state,
                job_id,
            ),
        )


@_reading
def attend_running_for_run(run_id: str) -> dict[str, Any] | None:
    """The attendant currently on this run, if there is one."""
    row = (
        _read_connection()
        .execute(
            "SELECT * FROM attend_sessions WHERE run_id = ? AND status = ?"
            " ORDER BY started_at DESC LIMIT 1",
            (run_id, ATTEND_RUNNING),
        )
        .fetchone()
    )
    return _attend_row(row) if row is not None else None


@_reading
def attend_latest_for_run(run_id: str) -> dict[str, Any] | None:
    """The most recent attendant on this run, running or not — the pane's one link."""
    row = (
        _read_connection()
        .execute(
            "SELECT * FROM attend_sessions WHERE run_id = ? ORDER BY started_at DESC LIMIT 1",
            (run_id,),
        )
        .fetchone()
    )
    return _attend_row(row) if row is not None else None


@_reading
def attend_latest_by_run() -> dict[str, dict[str, Any]]:
    """The latest attendance per run, for the projection that links a blocked row to it."""
    rows = _read_connection().execute(
        "SELECT * FROM attend_sessions ORDER BY started_at ASC"
    )
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        record = _attend_row(row)
        run_id = str(record.get("run_id") or "")
        if run_id:
            latest[run_id] = record
    return latest


@_reading
def attend_recent(limit: int = 200) -> list[dict[str, Any]]:
    """The latest attendances, newest first."""
    rows = _read_connection().execute(
        "SELECT * FROM attend_sessions ORDER BY started_at DESC LIMIT ?",
        (max(1, limit),),
    )
    return [_attend_row(row) for row in rows]


@_reading
def attend_get(job_id: str) -> dict[str, Any] | None:
    row = (
        _read_connection()
        .execute("SELECT * FROM attend_sessions WHERE job_id = ?", (job_id,))
        .fetchone()
    )
    return _attend_row(row) if row is not None else None


@_reading
def attend_by_session(session_id: str) -> dict[str, Any] | None:
    """The attendance a session id belongs to — the pane routes on the session, not the job."""
    for row in _read_connection().execute("SELECT * FROM attend_sessions"):
        record = _attend_row(row)
        if session_id in record["session_ids"]:
            return record
    return None


@_reading
def attend_orphans() -> list[dict[str, Any]]:
    """Every row still claiming to be ``running`` — what boot recovery re-checks."""
    rows = _read_connection().execute(
        "SELECT * FROM attend_sessions WHERE status = ? ORDER BY started_at ASC",
        (ATTEND_RUNNING,),
    )
    return [_attend_row(row) for row in rows]



DISPATCH_PENDING = "pending"
DISPATCH_RUNNING = "running"
DISPATCH_DONE = "done"
DISPATCH_FAILED = "failed"
DISPATCH_CANCELLED = "cancelled"


def _dispatch_row(row: sqlite3.Row) -> dict[str, Any]:
    """A row with ``params`` back as the object it was enqueued with."""
    record = dict(row)
    raw = record.get("params") or ""
    try:
        record["params"] = json.loads(raw) if raw else {}
    except ValueError:
        record["params"] = {}
    return record


@_resilient
def dispatch_enqueue(
    item_id: str,
    *,
    queue: str,
    command: str,
    params: dict[str, Any] | None = None,
    enqueued_at: float | None = None,
) -> None:
    """Record a new item as ``pending``."""
    with _STORE.writing() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO dispatch_items (item_id, queue, command, params,"
            " status, run_id, pid, exit_code, enqueued_at, started_at, ended_at)"
            " VALUES (?, ?, ?, ?, ?, '', NULL, NULL, ?, NULL, NULL)",
            (
                item_id,
                queue,
                command,
                json.dumps(params or {}),
                DISPATCH_PENDING,
                float(enqueued_at if enqueued_at is not None else time.time()),
            ),
        )


@_resilient
def dispatch_start(
    item_id: str,
    *,
    run_id: str = "",
    pid: int | None = None,
    started_at: float | None = None,
) -> None:
    """Flip a `pending` row to `running` — called by the thread launching the process."""
    with _STORE.writing() as conn:
        conn.execute(
            "UPDATE dispatch_items SET status = ?, run_id = ?, pid = ?, started_at = ?"
            " WHERE item_id = ?",
            (
                DISPATCH_RUNNING,
                run_id,
                pid,
                float(started_at if started_at is not None else time.time()),
                item_id,
            ),
        )


@_resilient
def dispatch_finish(
    item_id: str,
    *,
    status: str,
    exit_code: int | None = None,
    ended_at: float | None = None,
) -> bool:
    """Flip a row to a terminal state (`done` / `failed` / `cancelled`) — but only if it is not terminal already."""
    with _STORE.writing() as conn:
        cursor = conn.execute(
            "UPDATE dispatch_items SET status = ?, exit_code = ?, ended_at = ?"
            " WHERE item_id = ? AND status IN (?, ?)",
            (
                status,
                exit_code,
                float(ended_at if ended_at is not None else time.time()),
                item_id,
                DISPATCH_PENDING,
                DISPATCH_RUNNING,
            ),
        )
        return cursor.rowcount > 0


@_resilient
def dispatch_cancel_pending(item_id: str) -> bool:
    """Cancel a still-`pending` item without ever spawning a process."""
    with _STORE.writing() as conn:
        cursor = conn.execute(
            "UPDATE dispatch_items SET status = ?, ended_at = ?"
            " WHERE item_id = ? AND status = ?",
            (DISPATCH_CANCELLED, time.time(), item_id, DISPATCH_PENDING),
        )
        return cursor.rowcount > 0


@_reading
def dispatch_get(item_id: str) -> dict[str, Any] | None:
    row = (
        _read_connection()
        .execute("SELECT * FROM dispatch_items WHERE item_id = ?", (item_id,))
        .fetchone()
    )
    return _dispatch_row(row) if row is not None else None


@_reading
def dispatch_list(queue: str, limit: int = 200) -> list[dict[str, Any]]:
    """Every item in this queue, newest first."""
    rows = _read_connection().execute(
        "SELECT * FROM dispatch_items WHERE queue = ? ORDER BY enqueued_at DESC LIMIT ?",
        (queue, max(1, limit)),
    )
    return [_dispatch_row(row) for row in rows]


@_reading
def dispatch_pending_for_queue(queue: str) -> list[dict[str, Any]]:
    """This queue's `pending` items, oldest first — the order they are launched in."""
    rows = _read_connection().execute(
        "SELECT * FROM dispatch_items WHERE queue = ? AND status = ? ORDER BY enqueued_at ASC",
        (queue, DISPATCH_PENDING),
    )
    return [_dispatch_row(row) for row in rows]


@_reading
def dispatch_running_for_queue(queue: str) -> list[dict[str, Any]]:
    """This queue's `running` items — its current occupancy."""
    rows = _read_connection().execute(
        "SELECT * FROM dispatch_items WHERE queue = ? AND status = ? ORDER BY started_at ASC",
        (queue, DISPATCH_RUNNING),
    )
    return [_dispatch_row(row) for row in rows]


@_reading
def dispatch_orphans() -> list[dict[str, Any]]:
    """Every row still claiming to be `running`, across every queue — what boot recovery re-checks (§3.5)."""
    rows = _read_connection().execute(
        "SELECT * FROM dispatch_items WHERE status = ? ORDER BY started_at ASC",
        (DISPATCH_RUNNING,),
    )
    return [_dispatch_row(row) for row in rows]
