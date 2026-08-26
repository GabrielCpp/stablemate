"""Embedded SQLite persistence for telemetry — the durable, searchable half of
groom's collector role (stdlib ``sqlite3``, no database server).

The in-memory ring in :mod:`groom.state` stays the hot cache for the live
dashboard and alert-rule state; this file is the queryable fleet index that
survives ``groom serve`` restarts. Each run's own ``events.jsonl`` on disk
remains the append-only record-of-truth — SQLite exists for cross-run search
(slowest nodes, error spans, cost per run, who cap-waited), not as the primary
record. Spans older than the retention window are pruned to bound growth.

One process-wide connection, and it is *not* free of locks or of failure. Reads
run inline on the event loop while every write goes to an ``asyncio.to_thread``
worker, so a connection — which has exactly one transaction and one snapshot — is
shared across threads: :class:`_Store` therefore holds it behind an ``RLock``, opens
it in real autocommit (``isolation_level=None``) so no failure path can strand an
open transaction, and wraps multi-statement writes in an explicit ``BEGIN IMMEDIATE``.
When a statement fails anyway the connection is recycled and the call retried once
(:func:`_resilient`), because a collector meant to run for weeks cannot answer a
wedged handle with a 500 forever. :func:`health` is what that looks like from outside.
"""

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

logger = logging.getLogger(__name__)

# Days of span/metric history to keep; pruned at startup and on a periodic tick.
RETENTION_DAYS = float(os.environ.get("GROOM_RETENTION_DAYS", "14"))
# How far back the fleet/telemetry views (run_summaries, live_status) scan. The
# whole DB is retained for `RETENTION_DAYS` and stays queryable with raw SQL, but a
# live-ops dashboard only wants recent runs, and bounding the scan here is what keeps
# these queries from doing a full-table GROUP BY / window-function pass that grows
# with total history rather than with what's on screen. Default 24h.
ACTIVE_WINDOW_S = float(os.environ.get("GROOM_ACTIVE_WINDOW_S", "86400"))
# A hard ceiling on rows the live_status window function returns, so a pathological
# metric-cardinality run can't make one query materialize an unbounded result set.
_LIVE_STATUS_CAP = 500
# Logs are one row per line, not one per node visit, so they outgrow spans by
# orders of magnitude on a long run — hence a separate, shorter default window.
LOG_RETENTION_DAYS = float(os.environ.get("GROOM_LOG_RETENTION_DAYS", "3"))
# Pure-liveness counters get a shorter window still. They tick every ~10s per open
# node for the whole life of a run, which on a week-long run is millions of rows:
# in one real store `workhorse.run.heartbeat` alone was 1.77M of 2.21M metric rows,
# 1.23M of them from a single run. Nothing reads their history — the alert rules
# fold heartbeats into an in-memory cache at ingest (groom.alerts.ingest_metrics)
# and `live_status` reads only the newest point per (run_id, name) — so retaining
# a fortnight of them buys nothing and costs most of the file. The *gauges*
# (idle_s, elapsed_s, node.active) are excluded: their history is diagnostic (a
# climbing idle_s is how a wedged turn looks) and they are two orders of magnitude
# smaller.
LIVENESS_RETENTION_DAYS = float(os.environ.get("GROOM_LIVENESS_RETENTION_DAYS", "1"))
_LIVENESS_METRICS = (
    "workhorse.run.heartbeat",
    "workhorse.turn.heartbeat",
    "workhorse.cap_wait.heartbeat",
)

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
    head_end TEXT
);
CREATE INDEX IF NOT EXISTS spans_run ON spans(run_id, start_ts);
CREATE INDEX IF NOT EXISTS spans_node ON spans(node);
CREATE INDEX IF NOT EXISTS spans_status ON spans(status);
CREATE TABLE IF NOT EXISTS metrics (
    run_id TEXT NOT NULL DEFAULT '',
    name   TEXT NOT NULL,
    ts     REAL NOT NULL,
    value  REAL NOT NULL,
    attrs_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS metrics_run ON metrics(run_id, name, ts);
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
    head     TEXT
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
"""

def db_path() -> Path:
    """``$GROOM_DB`` (tests point it at a temp file), else the platform data
    dir — read per call so a test's env var takes effect without reimport."""
    env = os.environ.get("GROOM_DB")
    if env:
        return Path(env)
    return Path(user_data_dir("groom")) / "groom.db"


# Columns added to `spans` after the table first shipped. CREATE TABLE IF NOT
# EXISTS silently does nothing on an existing DB, so a new column has to be
# ALTERed in or every query naming it fails on a pre-existing groom.db.
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
    ("est_cost_usd", "REAL"),
    ("priced_model", "TEXT"),
)

#: The same, for `logs`. A log record carries the head observed when it was *emitted*
#: rather than one for the whole run, because a workflow — or the agent inside a turn —
#: may move HEAD at any point, and a run-level value would be wrong for most of the
#: records. NULL means nothing observed a tree, which is not the same as an unknown hash.
_ADDED_LOG_COLUMNS = (("head", "TEXT"),)

# OTel attribute key -> the `spans` column it is promoted to. OTel's attribute model
# is a flat dict whose keys merely *look* dotted, so `usage.output_tokens` is stored
# in attrs_json as a literal key with a dot in it and
# `json_extract(attrs_json,'$.usage.output_tokens')` silently returns NULL — SQLite
# reads the dot as navigation. Only `'$."usage.output_tokens"'` works. Rather than
# make every caller remember that, the handful of fields every cost query wants get
# real columns. The rest stay in attrs_json (quote the key), and the promoted ones
# stay there too, so queries written against the old shape keep working.
_PROMOTED_SPAN_COLUMNS = (
    ("duration_ms", "duration_ms", int),
    ("total_cost_usd", "total_cost_usd", float),
    ("usage.input_tokens", "input_tokens", int),
    ("usage.output_tokens", "output_tokens", int),
    ("usage.cache_read_input_tokens", "cache_read_tokens", int),
    ("usage.cache_creation_input_tokens", "cache_creation_tokens", int),
    # Observations, not assertions: the pair being unequal is the record that something
    # moved HEAD inside the span, and the store says nothing about why. A span over a
    # tree nobody looked at carries neither.
    ("git.head.start", "head_start", str),
    ("git.head.end", "head_end", str),
)

#: Promoted from the decoded span record rather than from its OTel attributes — these
#: two are *resource* attributes, which `otlp.parse_traces` lifts into named fields.
_PROMOTED_SPAN_FIELDS = ("pid", "resume_generation")

#: Computed here rather than reported by anyone: what this turn's tokens are worth at
#: the rate card in `groom.prices`. Its own column, never folded into `total_cost_usd` —
#: what a vendor billed and what a rate card says are different claims, and a sum of the
#: two is a number no one can act on. NULL when the model has no published rate here,
#: which is what makes the unpriced share of a report countable.
#:
#: `priced_model` is the other half of that claim: *which* rate produced the estimate.
#: It is usually the model the turn reported, but not always — a turn whose harness
#: recorded an alias (`sonnet`) is priced by the concrete id its session store names, and
#: an estimate whose provenance is invisible is one nobody can check or correct.
_DERIVED_SPAN_COLUMNS = ("est_cost_usd", "priced_model")

#: Every column `insert_spans` writes past the plain ones, in order.
_SPAN_VALUE_COLUMNS = (
    *(column for _key, column, _cast in _PROMOTED_SPAN_COLUMNS),
    *_PROMOTED_SPAN_FIELDS,
    *_DERIVED_SPAN_COLUMNS,
)


def _promoted(span: dict[str, Any], attrs: dict[str, Any]) -> tuple[Any, ...]:
    """The promoted and derived columns' values for one span, in `_SPAN_VALUE_COLUMNS` order.

    A missing or unparseable field yields NULL, never 0. Workhorse's normalizer draws
    the same distinction on purpose (`runner/usage.py`): a harness that does not report
    money reports nothing rather than `0.0`, because averaging a real zero together
    with an unknown understates spend. Coercing to 0 here would throw that away at the
    last step.
    """
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
    """This turn's tokens at the rate card, or NULL when the model is not in it.

    Reads the token counts already cast for the promoted columns rather than the raw
    attributes, so the estimate and the counts a report shows beside it can never
    disagree about what the turn used.
    """
    return prices.estimate(
        model,
        tokens.get("input_tokens"),
        tokens.get("output_tokens"),
        tokens.get("cache_read_tokens"),
        tokens.get("cache_creation_tokens"),
    )


def _migrate(conn: sqlite3.Connection) -> None:
    for table, added in (("spans", _ADDED_SPAN_COLUMNS), ("logs", _ADDED_LOG_COLUMNS)):
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for column, decl in added:
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")  # noqa: S608


_P = ParamSpec("_P")
_T = TypeVar("_T")

# How long after recycling the connection a further failure is answered by raising
# rather than by reopening again. A wedged handle heals on the first reopen; a broken
# *file* (disk full, corruption) would otherwise close-and-open on every request.
REOPEN_COOLDOWN_S = 5.0


@dataclass(frozen=True, slots=True)
class StoreHealth:
    """What the store would say if asked whether it is still storing.

    ``ok`` is not "the last call succeeded" but "nothing has failed since the last
    successful reopen" — the distinction that matters after a two-week serve, where
    a single healed blip and an hour of dropped batches look identical in a counter.
    """

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
    """The process's one SQLite handle, and the discipline that keeps it usable.

    Three things are load-bearing and each of them was learned from a serve that had
    silently stopped storing 13 hours earlier:

    * ``isolation_level=None``. Under Python's legacy implicit-transaction mode, any
      exception between the implicit ``BEGIN`` and the ``commit()`` leaves the
      connection inside a transaction; every later ``SELECT`` joins it and re-pins the
      read snapshot, and every later write dies of ``SQLITE_BUSY_SNAPSHOT`` — forever,
      because nothing reopened. Autocommit removes the failure mode rather than
      handling it.
    * one ``RLock`` around every statement. ``check_same_thread=False`` buys memory
      safety from SQLite's serialized mode and nothing at the transaction level, and a
      connection has exactly one transaction: without the lock a worker thread's write
      and the event loop's inline read are the same transaction. It is also what makes
      :meth:`recycle` safe — closing a handle another thread is mid-``executemany`` on
      is not a recovery.
    * :meth:`recycle`. The handle is disposable; the file is not.
    """

    def __init__(self, monotonic: Callable[[], float] = time.monotonic) -> None:
        # Injected so the reopen cooldown is testable without a real sleep.
        self.monotonic = monotonic
        self.lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._path: Path | None = None
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
                # `db_path()` is read per call so a test's `$GROOM_DB` takes effect;
                # honour that here too rather than answering the old file.
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
        # An fsync per commit is the wrong trade for this file. Every OTLP batch is one
        # commit, so `FULL` costs a disk sync per export of every live run — and what it
        # buys is durability of the last few commits across a power cut, over a table
        # that is explicitly not the record of truth (each run's `events.jsonl` is).
        # `NORMAL` under WAL cannot corrupt the database; it can only lose commits newer
        # than the last checkpoint, which the next export replaces anyway.
        conn.execute("PRAGMA synchronous=NORMAL")
        # The CLI, `groom export` and the test suite are separate processes on this same
        # file; without a busy timeout a concurrent writer is an instant "database is
        # locked" rather than a wait of a few milliseconds.
        conn.execute("PRAGMA busy_timeout=5000")
        conn.executescript(_SCHEMA)
        _migrate(conn)
        return conn

    @contextmanager
    def writing(self) -> Iterator[sqlite3.Connection]:
        """One atomic write. `BEGIN IMMEDIATE`, and `ROLLBACK` on any exception.

        ``IMMEDIATE`` rather than a deferred ``BEGIN``: the write lock is taken up
        front, so a transaction cannot fail half-way through on a snapshot upgrade —
        which is the shape that used to strand one.
        """
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
        """Throw the handle away so the next call opens a fresh one.

        Raises the original exception instead when it is called again inside
        ``REOPEN_COOLDOWN_S``: one reopen fixes a wedged connection, and a second
        one this soon means the file itself is the problem, which reopening will
        not fix and thrashing will only obscure.
        """
        with self.lock:
            self._failures += 1
            self._last_error = f"{type(exc).__name__}: {exc}"
            self._last_error_ts = time.time()
            now = self.monotonic()
            if self._reopens and now - self._last_reopen_at < REOPEN_COOLDOWN_S:
                logger.error("groom.store: %s failed again while cooling down: %s", where, exc)
                raise exc
            self._close_quietly()
            self._reopens += 1
            self._last_reopen_at = now
            logger.error("groom.store: recycling the connection after %s in %s", exc, where)

    def reset(self) -> None:
        """Close the connection and forget every failure with it (tests switch
        ``$GROOM_DB`` between cases, and a counter that survived would be another
        case's)."""
        with self.lock:
            self._close_quietly()
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

    def note_ok(self) -> None:
        """Stamp a statement that ran. What :attr:`StoreHealth.ok` is measured against:
        a failure older than the last good call has been healed, one newer has not."""
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
            # A failure older than the last statement that ran is history; one newer
            # than it is the store being down right now.
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


_STORE = _Store()


def _resilient(fn: Callable[_P, _T]) -> Callable[_P, _T]:
    """Serialize a store call, and heal the connection under it exactly once.

    The retry calls the *undecorated* body, so depth is bounded at two by
    construction rather than by a counter. Decorate leaf functions only: a decorated
    function that calls another one multiplies attempts.
    """

    # Read once, and defensively: `Callable` is not necessarily a function, and the
    # name is only ever a label in a log line.
    name = getattr(fn, "__name__", "store call")

    @functools.wraps(fn)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _T:
        with _STORE.lock:
            try:
                result = fn(*args, **kwargs)
            except sqlite3.Error as exc:
                # `sqlite3.Error`, the base, deliberately: the wedge arrives as
                # OperationalError and a recycled handle as ProgrammingError, and
                # sorting "recoverable" from the rest by message or errno is a guess.
                # A genuine IntegrityError fails the same way on the retry and
                # propagates, costing one reopen.
                _STORE.recycle(exc, name)
            else:
                _STORE.note_ok()
                return result
            result = fn(*args, **kwargs)
            _STORE.note_ok()
            return result

    return wrapper


def _connection() -> sqlite3.Connection:
    return _STORE.connect()


def reset() -> None:
    """Close the module connection so the next call reopens (tests switch
    GROOM_DB between cases)."""
    _STORE.reset()


def health() -> StoreHealth:
    """Whether the collector is still storing what it is told, and since when."""
    return _STORE.health()


def health_dict() -> dict[str, Any]:
    """:func:`health` as JSON for the dashboard state payload."""
    return asdict(_STORE.health())


@_resilient
def insert_spans(spans: list[dict[str, Any]]) -> None:
    """Upsert decoded spans (see groom.otlp.parse_traces). INSERT OR REPLACE:
    an exporter retry re-sending a batch must not error or duplicate."""
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
                    s["span_id"], s["trace_id"], s.get("parent_id", ""), s.get("run_id", ""),
                    s.get("workflow", ""), s.get("repo", ""), s.get("branch", ""),
                    s.get("node", ""), s.get("name", ""), s.get("run_dir", ""),
                    s.get("start_ts", 0.0), s.get("end_ts", 0.0), s.get("status", "UNSET"),
                    json.dumps(s.get("attrs") or {}),
                    *_promoted(s, s.get("attrs") or {}),
                )
                for s in spans
            ],
        )


@_resilient
def insert_metrics(points: list[dict[str, Any]]) -> None:
    """Append decoded metric points (see groom.otlp.parse_metrics).

    Plain INSERT, and a point has no id to key on, so a batch the receiver answered
    503 to and the exporter re-sent can land twice. That is the trade the 503 buys:
    every reader of this table asks it by recency or by aggregate, where a duplicate
    is cosmetic, and the alternative on the other side of the choice is a batch the
    exporter drops for good.
    """
    if not points:
        return
    with _STORE.writing() as conn:
        conn.executemany(
            "INSERT INTO metrics (run_id, name, ts, value, attrs_json) VALUES (?, ?, ?, ?, ?)",
            [
                (
                    p.get("run_id", ""), p["name"], p.get("ts", 0.0),
                    float(p.get("value", 0.0)), json.dumps(p.get("attrs") or {}),
                )
                for p in points
            ],
        )


def _log_head(attrs: dict[str, Any]) -> str | None:
    """The commit this record was emitted on, or NULL for a record nobody observed one
    for. Kept out of the promoted-column machinery above because that one reads spans."""
    raw = attrs.get("head")
    return raw if isinstance(raw, str) and raw else None


@_resilient
def insert_logs(records: list[dict[str, Any]]) -> None:
    """Append decoded log records (see groom.otlp.parse_logs).

    Plain INSERT, unlike spans: a log record has no id to key on and there is no
    natural primary key to invent. The exporter *does* retry a 5xx, so a batch this
    store refused can arrive twice — accepted deliberately (see
    :func:`insert_metrics`) rather than paid for with a synthetic dedup key and the
    schema migration one would need.
    """
    if not records:
        return
    with _STORE.writing() as conn:
        conn.executemany(
            "INSERT INTO logs (run_id, workflow, run_dir, node, logger, severity, body,"
            " ts, trace_id, attrs_json, head) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    r.get("run_id", ""), r.get("workflow", ""), r.get("run_dir", ""),
                    r.get("node", ""), r.get("logger", ""), r.get("severity", "INFO"),
                    r.get("body", ""), r.get("ts", 0.0), r.get("trace_id", ""),
                    json.dumps(r.get("attrs") or {}),
                    _log_head(r.get("attrs") or {}),
                )
                for r in records
            ],
        )


# Ordered loudest-first; an index into this is "at least this severe".
_SEVERITY_ORDER = ("FATAL", "ERROR", "WARNING", "INFO", "DEBUG", "TRACE")


@_resilient
def query_logs(
    run: str = "",
    node: str = "",
    level: str = "",
    contains: str = "",
    limit: int = 200,
    before_ts: float | None = None,
) -> list[dict[str, Any]]:
    """The log search behind ``groom logs``, newest first.

    ``level`` is a floor, not an equality match — asking for WARNING and being
    shown warnings but no errors would be the opposite of useful. ``before_ts`` is
    the keyset cursor: pass the ``ts`` of the last row of the previous page to fetch
    the next, so a chatty run's logs page instead of loading a whole run at once.
    """
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
    conn = _connection()
    rows = conn.execute(
        f"SELECT run_id, workflow, run_dir, node, logger, severity, body, ts, trace_id,"  # noqa: S608
        f" attrs_json FROM logs {clause} ORDER BY ts DESC LIMIT ?",
        (*params, limit),
    ).fetchall()
    return [
        {**dict(row), "attrs": json.loads(row["attrs_json"] or "{}")} for row in rows
    ]


def _promoted_or_attr(column: str, key: str) -> str:
    """The promoted column, falling back to the attribute it was promoted from.

    The columns are populated at ingest and deliberately not backfilled, so every
    span already in the store has NULL in them. Without this fallback an aggregate
    would read as "this run cost nothing" for the whole retention window after the
    columns ship — a wrong answer, and a much worse one than a slow answer, since
    nothing about it looks like missing data.

    Note the quoting. OTel attribute keys are flat strings that merely look nested,
    so the literal key is `usage.output_tokens` and the JSON path has to quote it;
    unquoted, SQLite reads the dot as navigation and silently returns NULL.
    """
    return f"COALESCE({column}, json_extract(attrs_json, '$.\"{key}\"'))"


_cost = _promoted_or_attr("total_cost_usd", "total_cost_usd")
_duration = _promoted_or_attr("duration_ms", "duration_ms")
_output = _promoted_or_attr("output_tokens", "usage.output_tokens")
_input = _promoted_or_attr("input_tokens", "usage.input_tokens")
_cache_read = _promoted_or_attr("cache_read_tokens", "usage.cache_read_input_tokens")
_cache_write = _promoted_or_attr(
    "cache_creation_tokens", "usage.cache_creation_input_tokens"
)

#: `est_cost_usd` is derived here rather than reported by a harness, so — unlike the
#: promoted columns — there is no attribute to fall back to for a span that predates
#: it. History gets an estimate only by being repriced, which is why this is a command
#: and not a COALESCE.
_ESTIMABLE = (
    "name = 'agent_turn' AND ("
    f"{_input} IS NOT NULL OR {_output} IS NOT NULL"
    f" OR {_cache_read} IS NOT NULL OR {_cache_write} IS NOT NULL)"
)


@_resilient
def unpriced_models(run: str = "") -> dict[str, int]:
    """Models with turns the rate card cannot price, and how many turns each has.

    Answers "what would I gain by adding a rate" without writing anything, which is
    what makes it safe to print from a bare `groom prices`.
    """
    clauses = [_ESTIMABLE]
    params: list[Any] = []
    if run:
        clauses.append("run_id = ?")
        params.append(run)
    conn = _connection()
    rows = conn.execute(
        # By the rate that priced it where there is one, so a turn whose alias was
        # resolved against its session store stops reading as a gap in the card.
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
    """Recompute `est_cost_usd` over turns already in the store.

    Two occasions want this and they want opposite defaults, so both are here: after
    adding a model to `prices.toml` only the rows that never got an estimate need one
    (`missing_only`, the default), and after *correcting* a rate every row priced at
    the old one is wrong (`missing_only=False`).

    Returns what was touched and, more usefully, what could not be: `unpriced` maps
    each model with token counts and no rate to how many of its turns are affected.
    That list is the answer to "what do I add to the override file", and printing it
    is the only thing that keeps an estimate's coverage from silently being a subset.
    """
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
        # `priced_model` first: a turn whose alias was resolved against its session store
        # must reprice at the concrete model's rate, not fall back to the alias the
        # harness reported and lose the estimate it already has.
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


@_resilient
def _estimable_turns(clauses: list[str], params: list[Any]) -> list[sqlite3.Row]:
    """Turns matching `clauses`, with everything pricing one needs already coalesced."""
    return (
        _connection()
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


@_resilient
def unpriceable_turns(run: str = "") -> list[dict[str, Any]]:
    """Turns with tokens, no estimate, and a model no rate covers.

    The input to any recovery that goes looking outside the span for what the model
    really was — the turn's own attributes have already been shown not to answer.
    """
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
    """Write `(est_cost_usd, priced_model, span_id)` triples; rows touched.

    The model is written with the estimate and never separately: a stored estimate whose
    rate cannot be named is one no later pass can recompute or disprove.
    """
    with _STORE.writing() as conn:
        conn.executemany(
            "UPDATE spans SET est_cost_usd = ?, priced_model = ? WHERE span_id = ?", updates
        )
    return len(updates)


@_resilient
def node_costs(run: str = "", limit: int = 100) -> list[dict[str, Any]]:
    """Per-node agent spend for a run: where the money and the rework went.

    Only `agent_turn` spans are counted. A node span wraps its turn, so totalling
    both would double every figure; and a node with no turn under it (an in-process
    `self.call`) spent no agent money by definition.

    `turns_per_work_id` is the rework signal. A workflow stamps `work_id` as a label
    (the coder workflow uses the story slug), so a node that averages one turn per
    work item ran once per story and a node averaging four re-ran three times. That
    ratio, not the raw turn count, is what separates an expensive node from a
    *looping* one.

    Cost is summed over rows where it is non-NULL, and two counts say how trustworthy
    that sum is — because a harness can decline to price a turn in two different ways
    and only one of them is visible as a gap:

    * `cost_turns` — turns carrying any cost at all. codex reports **none** under
      subscription auth, so on a codex run this is 0 and every `cost_usd` is NULL.
    * `zero_cost_turns` — turns that reported cost `0` *while reporting output tokens*.
      This is the dangerous one. opencode's cost depends on the provider behind it, not
      on opencode: through OpenRouter a turn reports real money, and through a
      subscription OAuth provider the identical turn reports a literal `0`. A NULL is
      excluded from the sum and shows up as a gap; a zero is summed, so a run that
      spent forty minutes totals $0.00 and looks complete. A turn that emitted tokens
      did not cost nothing — it was not priced. (A genuinely free model reports the
      same way, which is why this is surfaced rather than corrected.)

    So the unit of cost coverage is **harness × provider**, not harness. `backends`
    names who ran each node; the CLI says out loud when either count implies the total
    is partial.

    `est_cost_usd` is the same turns priced at `groom.prices`' rate card, over the
    `est_turns` of them whose model it knows. It is reported *beside* `cost_usd` and
    never added to it: one is what a vendor billed and the other is what tokens are
    worth, and a column mixing them answers nothing. Rows only carry it once
    :func:`reprice` has run over them.
    """
    clauses, params = ["name = 'agent_turn'"], []
    if run:
        clauses.append("run_id = ?")
        params.append(run)
    conn = _connection()
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
        # Minutes, not turns, breaks the tie: on a run where nothing priced itself the
        # cost key is uniformly NULL, and ranking the remainder by turn count would put
        # a node with many cheap turns above one that spent an hour in three.
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


#: Exit-rate thresholds for :func:`loop_convergence`. A gate that accepts four times
#: in five is doing its job; one that accepts one time in five is not a gate, it is a
#: budget being spent. The boundaries are round numbers chosen to be legible, not
#: fitted — the number to act on is `excess_cost_usd`, and the verdict only sorts.
_LOOP_VERDICTS = ((0.8, "converged"), (0.5, "loose"), (0.3, "churning"), (0.0, "thrashing"))

#: Below this many work items a lap distribution says nothing: one story that took
#: four passes is an anecdote, and calling it "thrashing" would put noise at the top
#: of a report whose whole purpose is ranking.
MIN_LOOP_WORK_ITEMS = 3


@dataclass(frozen=True, slots=True)
class Lap:
    """One turn of a loop, as the three numbers ranking it needs.

    `cost` is what the harness billed and `est` is what `groom.prices` says the tokens
    were worth; `suspect_zero` marks the turn that reported exactly $0 while emitting
    output. They stay three fields rather than one resolved number because collapsing
    them here would decide, inside the store, whether a report is quoting a bill or a
    rate card — a distinction the caller has to be able to label.
    """

    cost: float | None
    suspect_zero: bool
    est: float | None


@_resilient
def loop_convergence(
    run: str = "",
    workflow: str = "",
    min_work_items: int = MIN_LOOP_WORK_ITEMS,
    since_ts: float | None = None,
) -> list[dict[str, Any]]:
    """Per-node lap distributions: which review→rework loops converge, and what the
    ones that don't are costing.

    `node_costs` reports `turns_per_work_id`, which is this function's `mean_laps`.
    The mean alone cannot separate the two ways a node averages four turns — *every*
    work item taking four passes, versus most taking one and a handful taking twenty —
    and those want opposite fixes. So the unit here is the **lap count per work item**,
    and what is reported is its shape.

    The headline is `exit_rate` = `work_items / turns`: the probability that any given
    lap is the last one for that work item. It is the maximum-likelihood estimate of
    the per-lap acceptance probability of a memoryless loop, which is what a review
    gate is — it re-reads a rewritten artifact with no memory of how many times it has
    already objected. Read it as *how often this gate says yes*. A gate at 0.8 accepts
    four times in five; a gate at 0.2 asks five times before it is satisfied, and the
    four refusals are the churn.

    `since_ts` bounds the window from below. A caller that reuses a run id — a benchmark
    harness replays the same trial under the same name every round — otherwise pools every
    round that ever ran under that id, and the union reads as one very expensive round.

    `excess_turns` and `excess_cost_usd` are the laps after the first, and their money
    — the part of the bill that exists only because the loop did not converge. That is
    the number to rank by; the verdict is a label on it. Cost is attributed per turn
    rather than pro-rated, so a loop whose repeat laps are cheaper than its first (a
    rework prompt is usually shorter than the original) is not overcharged.

    `max_laps` and `at_max` are reported without a verdict attached, deliberately. A
    loop bounded by a `MAX_*` budget is censored — every work item that would have run
    longer stops at exactly the cap — so a pile at the maximum is *suggestive* of a
    budget being exhausted rather than a gate being satisfied. It is only suggestive:
    this module cannot see the workflow's constants, and a naturally long tail lands in
    the same place. Whoever reads a big `at_max` should go look at the `MAX_*` for that
    loop, which is why the number is here at all.

    Work items are keyed by `(run_id, work_id)`. Story slugs repeat across runs — every
    coder run has an `01-*` — so keying on the slug alone would silently merge one
    story's laps in three runs into a single nine-lap item and report a converging loop
    as a thrashing one.

    Two counts keep the ranking honest, because a harness can decline to price a turn
    two ways and only one of them leaves a hole (`node_costs` documents this at length).
    `priced_turns` is the turns reporting any cost; `zero_cost_turns` is the turns
    reporting exactly `0` *while emitting output tokens*, which sum happily and make a
    thrashing node read as free. Under subscription auth a node can churn hundreds of
    laps for a reported $0, so ordering by `excess_cost_usd` alone would sort the worst
    loop in such a run to the bottom. `excess_turns` breaks the tie, and the CLI says
    out loud when the money is only partly observed.

    `est_cost_usd` / `excess_est_cost_usd` are the same two sums over `groom.prices`'
    rate card instead of the harness's report, across the `est_turns` of them whose
    model the table names. They are reported *beside* the billed figures and never
    added to them, exactly as in `node_costs`: one is what a vendor charged, the other
    is what the tokens are worth, and a loop under subscription auth has only the
    second. That is what makes a `$0` backend rankable at all — but only once its model
    has rates, so a report quoting the estimate must quote `est_turns` with it.

    Nodes with fewer than `min_work_items` items are dropped: see
    :data:`MIN_LOOP_WORK_ITEMS`.
    """
    clauses = ["name = 'agent_turn'", "json_extract(attrs_json, '$.work_id') IS NOT NULL"]
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
    rows = _connection().execute(
        "SELECT node, run_id,"  # noqa: S608 — clauses are literals; every value is bound
        " json_extract(attrs_json, '$.work_id') AS work_id,"
        f" {_cost} AS cost_usd, {_cost} = 0 AND COALESCE({_output}, 0) > 0 AS suspect_zero,"
        " est_cost_usd, start_ts"
        f" FROM spans WHERE {' AND '.join(clauses)} ORDER BY start_ts",
        params,
    ).fetchall()

    # node -> (run_id, work_id) -> [(cost, suspect_zero, est_cost) of each lap, in order]
    laps: dict[str, dict[tuple[str, str], list[Lap]]] = {}
    for row in rows:
        item = (row["run_id"], str(row["work_id"]))
        lap = Lap(row["cost_usd"], bool(row["suspect_zero"]), row["est_cost_usd"])
        laps.setdefault(row["node"], {}).setdefault(item, []).append(lap)

    report = [_loop_row(node, items) for node, items in laps.items()]
    report = [row for row in report if row["work_items"] >= min_work_items]
    report.sort(key=lambda row: (-(row["excess_cost_usd"] or 0.0), -row["excess_turns"]))
    return report


def _loop_row(node: str, items: dict[tuple[str, str], list[Lap]]) -> dict[str, Any]:
    counts = sorted(len(laps) for laps in items.values())
    turns, work_items = sum(counts), len(counts)
    exit_rate = work_items / turns
    peak = counts[-1]
    every = [lap for laps in items.values() for lap in laps]
    priced = [lap.cost for lap in every if lap.cost is not None]
    estimated = [lap.est for lap in every if lap.est is not None]
    # The laps after the first, by their own cost — not the total pro-rated.
    excess = [lap.cost for laps in items.values() for lap in laps[1:] if lap.cost is not None]
    excess_est = [lap.est for laps in items.values() for lap in laps[1:] if lap.est is not None]
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
        {
            (turn["trace_id"], turn["parent_id"] or turn["span_id"])
            for turn in turns
        }
    )
    costs = [float(turn["profile_cost_usd"]) for turn in turns if turn["profile_cost_usd"] is not None]
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
    """How many times each gate actually reached each verdict, cost aside.

    `_profile_groups` answers "what did this verdict cost", and it can only answer it over
    `agent_turn` spans, because turns are what carry a price. That makes it the wrong
    denominator for "how often": a label is stamped on every span opened after the state
    entry that set it, so a verdict routing to another agent turn is counted and a verdict
    routing to deterministic work is not. The bias is not random — it is exactly toward the
    expensive outcomes, so a rubber-stamp gate and a gate that changes everything can look
    alike. `qa.audit_verdict=stands` sat on 99 spans and 0 turns while `refuted` showed 4.

    A decision is a *transition*: the run of consecutive spans carrying one value counts
    once, and a value is re-counted after the dimension is cleared, which is how a gate
    reaching the same verdict on the next work item stays two decisions rather than one.
    Absence is what clearing looks like on the wire — `verdict_labels` emits only non-empty
    strings and every span is stamped with the whole current set.

    Traces are tracked separately so two flows in flight cannot alias each other's verdicts.
    Spans must arrive in start order; `run_profile` selects them that way.
    """
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
            key
            for key in current
            if key[0] == trace and key[1] not in present
        ]:
            del current[key]
    return [
        {"dimension": dimension, "value": value, "decisions": count}
        for (dimension, value), count in sorted(counts.items())
    ]


def _span_category(
    span: dict[str, Any], parent_keys: set[tuple[str, str]]
) -> str:
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
        (span["trace_id"], span["parent_id"])
        for span in spans
        if span["parent_id"]
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
    # Seconds, not a count: a `Counter` here is an int-valued mapping that happens to
    # accept `+=` on a float, so every duration accumulated below would be silently
    # truncated the moment anything read it as the int its type says it is.
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


@_resilient
def run_profile(run: str) -> dict[str, Any] | None:
    """Partition one run's retained wall time and aggregate its agent rework.

    This reads every span for the named run directly. Reusing :func:`query_spans`
    would silently truncate a long run at its search-page limit and produce a precise-
    looking partial total.
    """
    if not run:
        return None
    rows = _connection().execute(
        f"SELECT {_SPAN_COLUMNS}, duration_ms AS profile_duration_ms,"  # noqa: S608
        f" {_cost} AS profile_cost_usd, {_output} AS profile_output_tokens,"
        " resume_generation FROM spans WHERE run_id = ? ORDER BY start_ts",
        (run,),
    ).fetchall()
    spans = [
        {**dict(row), "attrs": json.loads(row["attrs_json"] or "{}")} for row in rows
    ]
    metric_bounds = _connection().execute(
        "SELECT MIN(ts) AS first_ts, MAX(ts) AS last_ts FROM metrics WHERE run_id = ?",
        (run,),
    ).fetchone()
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


# The spans-table columns, named explicitly rather than `SELECT *` so a schema
# migration can't silently change a query result's shape.
_SPAN_COLUMNS = (
    "span_id, trace_id, parent_id, run_id, workflow, repo, branch, node, name,"
    " run_dir, start_ts, end_ts, status, attrs_json"
)


@_resilient
def query_spans(
    run: str = "",
    node: str = "",
    status: str = "",
    slower_than: float | None = None,
    limit: int = 200,
    before_ts: float | None = None,
    since_ts: float | None = None,
) -> list[dict[str, Any]]:
    """The /traces search: filter the spans table, newest first. ``slower_than``
    is a minimum duration in seconds. ``before_ts`` is the keyset cursor — the
    ``start_ts`` of the last row of the previous page — so a broad query pages
    rather than materializing everything under one big LIMIT. Raw SQL against
    groom.db remains the ad-hoc escape hatch; this covers the common questions."""
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
    rows = _connection().execute(
        f"SELECT {_SPAN_COLUMNS} FROM spans WHERE {' AND '.join(clauses)}"  # noqa: S608 - literals
        " ORDER BY start_ts DESC LIMIT ?",
        params,
    ).fetchall()
    return [dict(row) for row in rows]


@_resilient
def run_summaries(
    limit: int = 50, now: float | None = None, run: str = ""
) -> list[dict[str, Any]]:
    """One row per run for the fleet/telemetry view: workflow, span window, and
    span/error counts. ``run`` narrows it to a single run — the detail pane's
    question, answered by the same aggregate.

    Deliberately says nothing about whether the run is *running*. It used to,
    via ``MAX(name LIKE 'run:%') AS finished``, which is a claim history cannot
    support: a root span proves some session of this run_id ended, and since
    ``--resume-run`` reuses the run_id (it comes from the run dir), that stayed
    true forever — a resumed run read as finished while it was mid-node. Liveness
    is a recency question and only :func:`live_run_ids` answers it.

    Bounded to the last ``ACTIVE_WINDOW_S`` so the GROUP BY scans recent history
    rather than the whole retained table; older runs stay queryable via raw SQL."""
    cutoff = (now if now is not None else time.time()) - ACTIVE_WINDOW_S
    params: list[Any] = [cutoff]
    run_clause = ""
    if run:
        run_clause = "AND run_id = ?"
        params.append(run)
    params.append(max(1, min(int(limit), 500)))
    rows = _connection().execute(
        "SELECT run_id, MAX(workflow) AS workflow, MAX(repo) AS repo,"
        " MIN(start_ts) AS first_ts, MAX(end_ts) AS last_ts,"
        " COUNT(*) AS span_count,"
        " SUM(CASE WHEN status = 'ERROR' THEN 1 ELSE 0 END) AS error_count"
        f" FROM spans WHERE run_id != '' AND end_ts >= ? {run_clause} GROUP BY run_id"  # noqa: S608 - literal clause, bound values
        " ORDER BY last_ts DESC LIMIT ?",
        params,
    ).fetchall()
    return [dict(row) for row in rows]


# The metrics that describe a run's LIVE state, as opposed to its history. Spans
# only export once they end, so for a run still in flight these are the whole
# picture: the trace of a hanging node does not exist yet and never will while it
# hangs.
_LIVE_METRICS = (
    "workhorse.run.heartbeat",
    "workhorse.node.elapsed_s",
    "workhorse.wait.active",
    "workhorse.wait.elapsed_s",
    "workhorse.turn.active",
    "workhorse.turn.elapsed_s",
    "workhorse.turn.idle_s",
    "workhorse.gas",
)

# How stale the last heartbeat may be before a run is presumed dead. Workhorse
# beats every ~10s, but the SDK's periodic reader only ships metrics every 60s by
# default, so anything under ~2 export intervals would flag healthy runs.
LIVE_AFTER_S = float(os.environ.get("GROOM_LIVE_AFTER_S", "180"))


@_resilient
def live_status(run: str = "", now: float | None = None) -> list[dict[str, Any]]:
    """Where each run is *right now*, newest heartbeat first.

    This is the question the spans table cannot answer. A node's span is written
    on completion, so the node a run is currently sitting in — the only one that
    matters when it will not finish — has no row anywhere in ``spans``. The
    heartbeat metric carries both the timestamp (is the process alive?) and the
    open node name (where is it?), so one query over ``metrics`` answers both.

    ``alive`` False means the process stopped emitting: dead, killed, or frozen.
    ``alive`` True with a large ``node_elapsed_s`` means the opposite failure —
    running fine, going nowhere.
    """
    now = now if now is not None else time.time()
    placeholders = ",".join("?" for _ in _LIVE_METRICS)
    params: list[Any] = list(_LIVE_METRICS)
    # Bound the window-function scan to recent points. A live run beats within
    # LIVE_AFTER_S (180s), so ACTIVE_WINDOW_S (24h) cannot hide one; without this the
    # CTE scanned every metric row ever ingested on each dashboard render.
    params.append(now - ACTIVE_WINDOW_S)
    run_clause = ""
    if run:
        run_clause = "AND run_id = ?"
        params.append(run)
    params.append(_LIVE_STATUS_CAP)
    rows = _connection().execute(
        # One row per (run, metric, attribute-set): the most recent point wins.
        f"""
        WITH latest AS (
            SELECT run_id, name, value, attrs_json, ts,
                   ROW_NUMBER() OVER (
                        PARTITION BY run_id, name ORDER BY ts DESC, rowid DESC
                   ) AS rn
            FROM metrics
            WHERE name IN ({placeholders}) AND run_id != '' AND ts >= ? {run_clause}
        )
        SELECT run_id, name, value, attrs_json, ts FROM latest WHERE rn = 1
        LIMIT ?
        """,  # noqa: S608 - placeholders/clause are literals, values are bound
        params,
    ).fetchall()

    runs: dict[str, dict[str, Any]] = {}
    for row in rows:
        entry = runs.setdefault(
            row["run_id"],
            {
                "run_id": row["run_id"], "workflow": "", "run_dir": "", "node": "",
                "node_elapsed_s": 0.0, "turn_active": None,
                "turn_elapsed_s": 0.0, "turn_idle_s": 0.0,
                "wait_kind": "", "wait_elapsed_s": 0.0, "gas": None,
                "last_beat_ts": 0.0, "alive": False,
            },
        )
        attrs = json.loads(row["attrs_json"] or "{}")
        if row["name"] == "workhorse.run.heartbeat":
            entry["last_beat_ts"] = row["ts"]
            entry["node"] = attrs.get("node", "")
            entry["alive"] = (now - row["ts"]) <= LIVE_AFTER_S
        elif row["name"] == "workhorse.node.elapsed_s":
            entry["node_elapsed_s"] = row["value"]
            entry["node"] = entry["node"] or attrs.get("node", "")
        elif row["name"] == "workhorse.wait.active":
            if row["value"] >= 1:
                entry["wait_kind"] = attrs.get("wait_kind", "unknown")
        elif row["name"] == "workhorse.wait.elapsed_s":
            entry["wait_elapsed_s"] = row["value"]
        elif row["name"] == "workhorse.turn.active":
            entry["turn_active"] = row["value"] >= 1
        elif row["name"] == "workhorse.turn.elapsed_s":
            entry["turn_elapsed_s"] = row["value"]
        elif row["name"] == "workhorse.turn.idle_s":
            entry["turn_idle_s"] = row["value"]
        elif row["name"] == "workhorse.gas":
            entry["gas"] = row["value"]
    for entry in runs.values():
        if entry["turn_active"] is False:
            entry["turn_idle_s"] = 0.0
            entry["turn_elapsed_s"] = 0.0
        if not entry["wait_kind"]:
            entry["wait_elapsed_s"] = 0.0

    # workflow/run_dir live on the resource, which only the spans table carries.
    for run_id, entry in runs.items():
        span = _connection().execute(
            "SELECT workflow, run_dir FROM spans WHERE run_id = ?"
            " ORDER BY start_ts DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        if span is not None:
            entry["workflow"] = span["workflow"]
            entry["run_dir"] = span["run_dir"]
    return sorted(runs.values(), key=lambda e: e["last_beat_ts"], reverse=True)


def live_run_ids(now: float | None = None) -> set[str]:
    """The run ids beating *right now* — the durable answer to the only liveness
    question that means anything.

    Read from the store rather than the in-memory hot cache on purpose: a groom
    that just restarted has an empty ``state.RUNS`` and would otherwise report
    every live run as not-running until each one's next export lands.
    """
    return {
        entry["run_id"] for entry in live_status(now=now) if entry.get("alive")
    }


# Path fragments that mark a run dir as a test process's, with no ambiguity:
# pytest's tmp_path factory roots every case under `pytest-of-<user>/`, and the
# workhorse/groom suites put their run dirs under `.workhorse-test/`. A path
# containing one of these is not a run anyone will come back to.
_TEST_RUN_DIR_MARKERS = ("/pytest-of-", "/.workhorse-test/", "/.groom-test/")

# `tempfile.mkdtemp`'s naming: `tmp` + random suffix, as a directory sitting
# directly in the temp root. This is the *heuristic* signal — a suite that builds
# its own scratch dir instead of using pytest's leaves no other trace — and it is
# why only the explicit purge consults it, never ingest.
_PY_TEMP_DIR = re.compile(r"^tmp[A-Za-z0-9_]{6,}$")


def _temp_roots() -> tuple[str, ...]:
    """Temp-dir prefixes a throwaway run dir sits under.

    ``/tmp`` is listed unconditionally, not just when it is this host's temp
    root: the producer may be a container while the collector is the host, and
    the run dir on the wire is the *producer's* path.
    """
    roots = {tempfile.gettempdir().rstrip("/"), "/tmp"}
    return tuple(f"{root}/" for root in sorted(roots) if root)


def is_test_run_dir(run_dir: str) -> bool:
    """Did this run dir certainly come from a test process?

    Deliberately narrow, because this is the predicate the ingest path drops on
    and a silent drop of real telemetry is worse than keeping some junk. Only
    the unambiguous markers count; ``/tmp`` alone does not.

    Workhorse already declines to export from a test process
    (``workhorse.otel._under_test``), so this is the collector's belt-and-braces
    half, covering producers on an older version or in a container.
    """
    if not run_dir:
        return False
    return any(marker in run_dir for marker in _TEST_RUN_DIR_MARKERS)


def is_scratch_run_dir(run_dir: str) -> bool:
    """Does this run dir look throwaway — a certain test dir, or a Python temp one?

    The wider net :func:`purge_test_runs` casts. It catches what
    :func:`is_test_run_dir` cannot: a suite that calls ``tempfile.mkdtemp``
    itself, which is how the biggest single junk run in a real store
    (150k+ spans) was written. It is a heuristic — a genuine run launched from a
    ``mkdtemp`` directory matches too — so it is confined to a command the
    operator runs deliberately and can preview with ``--dry-run``, rather than
    to the ingest path where the same guess would delete evidence unasked.
    """
    if is_test_run_dir(run_dir):
        return True
    for root in _temp_roots():
        if run_dir.startswith(root):
            return bool(_PY_TEMP_DIR.match(run_dir[len(root) :].split("/", 1)[0]))
    return False


@_resilient
def _test_run_ids() -> set[str]:
    """The run ids whose run dir says they were throwaway (:func:`is_scratch_run_dir`).

    Classified in Python rather than SQL because the predicate is a path
    heuristic, not a LIKE pattern. Only ``spans`` and ``logs`` carry ``run_dir``
    — ``metrics`` does not — so a run that only ever emitted heartbeats before
    its first node completed is invisible here and is left alone.
    """
    conn = _connection()
    pairs: set[tuple[str, str]] = set()
    for table in ("spans", "logs"):
        pairs.update(
            (row["run_id"], row["run_dir"])
            for row in conn.execute(
                f"SELECT DISTINCT run_id, run_dir FROM {table} WHERE run_dir != ''"  # noqa: S608 - literal table name
            )
        )
    return {run_id for run_id, run_dir in pairs if run_id and is_scratch_run_dir(run_dir)}


@_resilient
def test_run_ids() -> set[str]:
    """:func:`_test_run_ids`, with the store's heal-and-retry around it."""
    return _test_run_ids()


# Bound on ids per DELETE, so a store holding thousands of test runs does not
# build one statement with thousands of parameters (SQLite caps them).
_PURGE_CHUNK = 500


@_resilient
def purge_test_runs(dry_run: bool = False, vacuum: bool = True) -> dict[str, int]:
    """Delete every span/metric/log belonging to a test run.

    Returns ``{"runs": n, "spans": n, "metrics": n, "logs": n}`` — with
    ``dry_run`` the same counts are reported and nothing is deleted.

    ``vacuum`` rewrites the file afterwards: SQLite keeps freed pages for reuse,
    so a store where test runs were most of the rows stays its old size on disk
    until it is vacuumed, which is the visible half of the problem this solves.
    """
    run_ids = sorted(_test_run_ids())
    counts = {"runs": len(run_ids), "spans": 0, "metrics": 0, "logs": 0, "turns": 0}

    def sweep(conn: sqlite3.Connection) -> None:
        for start in range(0, len(run_ids), _PURGE_CHUNK):
            chunk = run_ids[start : start + _PURGE_CHUNK]
            marks = ",".join("?" * len(chunk))
            for table in ("spans", "metrics", "logs", "turns"):
                verb = "SELECT COUNT(*) AS n FROM" if dry_run else "DELETE FROM"
                cursor = conn.execute(f"{verb} {table} WHERE run_id IN ({marks})", chunk)  # noqa: S608 - literal table name, bound values
                counts[table] += cursor.fetchone()["n"] if dry_run else cursor.rowcount

    if dry_run:
        # Counting only: a `BEGIN IMMEDIATE` here would take the write lock to
        # answer a question that writes nothing.
        sweep(_connection())
        return counts
    with _STORE.writing() as conn:
        sweep(conn)
    if vacuum and counts["runs"]:
        # Outside the transaction — VACUUM cannot run inside one — but still under
        # the store lock, so it cannot rewrite the file under another thread's read.
        with _STORE.lock:
            _connection().execute("VACUUM")
    return counts


@_resilient
def insert_turns(rows: list[dict[str, Any]]) -> int:
    """Index archived turn records; how many rows the index gained or replaced.

    INSERT OR REPLACE on the visit key plus the session, so re-harvesting a run — which
    happens on every tick while it is live — updates the row of a transcript that has
    grown rather than duplicating it. No transcript text goes in here: the bodies live
    under :func:`groom.turns.transcripts_root` and this table is how they are found.
    """
    if not rows:
        return 0
    with _STORE.writing() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO turns (run_id, workflow, flow, node, session_id,"
            " generation, seq, ts, backend, source, path, bytes, sha256, head)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    r.get("run_id", ""), r.get("workflow", ""), r.get("flow", ""),
                    r.get("node", ""), r.get("session_id", ""), r.get("generation"),
                    r.get("seq"), float(r.get("ts") or 0.0), r.get("backend", ""),
                    r.get("source", ""), r.get("path", ""), int(r.get("bytes") or 0),
                    r.get("sha256", ""), r.get("head") or None,
                )
                for r in rows
            ],
        )
    return len(rows)


@_resilient
def query_turns(
    run: str = "",
    node: str = "",
    session: str = "",
    workflow: str = "",
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Archived turns, newest visit last — a node's laps read top to bottom.

    Ordered by the visit key rather than by ``ts``, because that is the order the run
    actually took them in and it survives a checkpoint rewind, which a wall clock read
    across two generations does not.
    """
    clauses: list[str] = []
    params: list[Any] = []
    for column, value in (
        ("run_id", run), ("node", node), ("session_id", session), ("workflow", workflow)
    ):
        if value:
            clauses.append(f"{column} = ?")
            params.append(value)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(max(1, limit))
    rows = _connection().execute(
        "SELECT run_id, workflow, flow, node, session_id, generation, seq, ts, backend,"
        f" source, path, bytes, sha256, head FROM turns {where}"  # noqa: S608 - bound values
        " ORDER BY run_id, generation, seq LIMIT ?",
        params,
    )
    return [dict(row) for row in rows]


@_resilient
def run_directories() -> list[dict[str, Any]]:
    """Every run telemetry has seen a directory for: run_id, run_dir, workflow.

    The run inventory the archive harvests from. Distinct rather than grouped, because a
    run that moved between directories is two rows here and both may hold records.
    """
    return [
        dict(row)
        for row in _connection().execute(
            "SELECT DISTINCT run_id, run_dir, workflow FROM spans"
            " WHERE run_dir != '' AND run_id != ''"
        )
    ]


@_resilient
def turns_before(cutoff: float) -> list[dict[str, Any]]:
    """Index rows for archived turns older than ``cutoff``. ``ts`` of 0 means the turn
    never recorded one, and an unstamped record is never aged out on a guess."""
    return [
        dict(row)
        for row in _connection().execute(
            "SELECT run_id, workflow, node, session_id, generation, seq, ts, path"
            " FROM turns WHERE ts > 0 AND ts < ?",
            (cutoff,),
        )
    ]


@_resilient
def delete_turns(cutoff: float) -> int:
    """Drop the index rows :func:`turns_before` returned; rows removed."""
    with _STORE.writing() as conn:
        removed = conn.execute("DELETE FROM turns WHERE ts > 0 AND ts < ?", (cutoff,)).rowcount
    return removed


@_resilient
def prune(retention_days: float = RETENTION_DAYS, now: float | None = None) -> int:
    """Drop spans/metrics/logs older than the retention window; rows removed.

    Logs get their own, shorter window (``GROOM_LOG_RETENTION_DAYS``): they are
    the highest-volume table by a wide margin — one row per log line rather than
    one per node visit — so holding them for the span retention would let a few
    chatty week-long runs dominate the file. The liveness counters get a shorter
    one again (``GROOM_LIVENESS_RETENTION_DAYS``, see ``_LIVENESS_METRICS``), for
    the same reason one step further: they are the highest-volume *metric* and the
    only one nothing reads the history of.

    ``turns`` is deliberately untouched. It indexes an archive on disk rather than
    telemetry, and the two are kept on different clocks on purpose: a transcript is
    wanted precisely when someone comes back to a run long after its spans have aged
    out. Its own knob is ``GROOM_TRANSCRIPT_RETENTION_DAYS`` (see :mod:`groom.turns`),
    and it defaults to keeping everything.
    """
    stamp = now if now is not None else time.time()
    cutoff = stamp - retention_days * 86400
    with _STORE.writing() as conn:
        removed = conn.execute("DELETE FROM spans WHERE end_ts < ?", (cutoff,)).rowcount
        removed += conn.execute("DELETE FROM metrics WHERE ts < ?", (cutoff,)).rowcount
        # Never longer than the table-wide window: a liveness setting above it would
        # otherwise read as "keep these longer", which the DELETE above cannot honour.
        liveness_cutoff = stamp - min(LIVENESS_RETENTION_DAYS, retention_days) * 86400
        placeholders = ",".join("?" * len(_LIVENESS_METRICS))
        removed += conn.execute(
            f"DELETE FROM metrics WHERE ts < ? AND name IN ({placeholders})",  # noqa: S608
            (liveness_cutoff, *_LIVENESS_METRICS),
        ).rowcount
        removed += conn.execute(
            "DELETE FROM logs WHERE ts < ?", (stamp - LOG_RETENTION_DAYS * 86400,)
        ).rowcount
    _checkpoint()
    _STORE.note_prune()
    return removed


def _checkpoint() -> None:
    """Fold the write-ahead log back into the database file, and truncate it.

    SQLite checkpoints on its own, but only when a writer finds no reader in the way —
    and this process writes continuously while the dashboard holds long read queries
    open, which is the one shape where auto-checkpointing can starve indefinitely. It
    is not a correctness problem and that is what makes it easy to miss: the WAL simply
    grows, and a 293 MB database was observed carrying a 376 MB WAL beside it. Called on
    the prune tick because a checkpoint after a large DELETE is also when it reclaims
    the most, and it is already off the event loop there.

    `TRUNCATE` rather than `PASSIVE`: passive is what was already happening and not
    working. A busy checkpoint returns rather than blocking, so a reader mid-query costs
    this tick and not the next one.
    """
    try:
        with _STORE.lock:
            row = _connection().execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    except sqlite3.Error as exc:
        # Never worth failing the prune over: the WAL being large is a disk-space
        # question, and the rows are already gone.
        logger.warning("groom: WAL checkpoint declined: %s", exc)
        return
    # The row is `(busy, log_frames, checkpointed)` and it is the only place SQLite
    # says a checkpoint did nothing. Discarding it is how a WAL grows for weeks with
    # no error anywhere: `busy == 1` means a reader was in the way and the file was
    # left alone. Recorded rather than merely logged so `/api/state` can show it.
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
