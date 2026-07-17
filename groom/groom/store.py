"""Embedded SQLite persistence for telemetry — the durable, searchable half of
groom's collector role (stdlib ``sqlite3``, no database server).

The in-memory ring in :mod:`groom.state` stays the hot cache for the live
dashboard and alert-rule state; this file is the queryable fleet index that
survives ``groom serve`` restarts. Each run's own ``events.jsonl`` on disk
remains the append-only record-of-truth — SQLite exists for cross-run search
(slowest nodes, error spans, cost per run, who cap-waited), not as the primary
record. Spans older than the retention window are pruned to bound growth.

groom is single-process/single-event-loop and writes are single-statement
inserts, so a plain module-level connection with autocommit is enough — no
pool, no locks (WAL mode keeps concurrent CLI reads from blocking the server).
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from platformdirs import user_data_dir

# Days of span/metric history to keep; pruned at startup (see create_app).
RETENTION_DAYS = float(os.environ.get("GROOM_RETENTION_DAYS", "14"))
# Logs are one row per line, not one per node visit, so they outgrow spans by
# orders of magnitude on a long run — hence a separate, shorter default window.
LOG_RETENTION_DAYS = float(os.environ.get("GROOM_LOG_RETENTION_DAYS", "3"))

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
    attrs_json TEXT NOT NULL DEFAULT '{}'
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
    attrs_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS logs_run ON logs(run_id, ts);
CREATE INDEX IF NOT EXISTS logs_node ON logs(run_id, node, ts);
CREATE INDEX IF NOT EXISTS logs_severity ON logs(severity);
"""

_conn: sqlite3.Connection | None = None


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
_ADDED_SPAN_COLUMNS = (("run_dir", "TEXT NOT NULL DEFAULT ''"),)


def _migrate(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(spans)")}
    for column, decl in _ADDED_SPAN_COLUMNS:
        if column not in existing:
            conn.execute(f"ALTER TABLE spans ADD COLUMN {column} {decl}")  # noqa: S608
    conn.commit()


def _connection() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        path = db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.executescript(_SCHEMA)
        _migrate(_conn)
    return _conn


def reset() -> None:
    """Close the module connection so the next call reopens (tests switch
    GROOM_DB between cases)."""
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None


def insert_spans(spans: list[dict[str, Any]]) -> None:
    """Upsert decoded spans (see groom.otlp.parse_traces). INSERT OR REPLACE:
    an exporter retry re-sending a batch must not error or duplicate."""
    if not spans:
        return
    conn = _connection()
    conn.executemany(
        "INSERT OR REPLACE INTO spans (span_id, trace_id, parent_id, run_id, workflow,"
        " repo, branch, node, name, run_dir, start_ts, end_ts, status, attrs_json)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                s["span_id"], s["trace_id"], s.get("parent_id", ""), s.get("run_id", ""),
                s.get("workflow", ""), s.get("repo", ""), s.get("branch", ""),
                s.get("node", ""), s.get("name", ""), s.get("run_dir", ""),
                s.get("start_ts", 0.0), s.get("end_ts", 0.0), s.get("status", "UNSET"),
                json.dumps(s.get("attrs") or {}),
            )
            for s in spans
        ],
    )
    conn.commit()


def insert_metrics(points: list[dict[str, Any]]) -> None:
    if not points:
        return
    conn = _connection()
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
    conn.commit()


def insert_logs(records: list[dict[str, Any]]) -> None:
    """Append decoded log records (see groom.otlp.parse_logs).

    Plain INSERT, unlike spans: a log record has no id to key on, and the SDK's
    BatchLogRecordProcessor does not retry a delivered batch, so there is nothing
    to deduplicate against and no natural primary key to invent.
    """
    if not records:
        return
    conn = _connection()
    conn.executemany(
        "INSERT INTO logs (run_id, workflow, run_dir, node, logger, severity, body,"
        " ts, trace_id, attrs_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                r.get("run_id", ""), r.get("workflow", ""), r.get("run_dir", ""),
                r.get("node", ""), r.get("logger", ""), r.get("severity", "INFO"),
                r.get("body", ""), r.get("ts", 0.0), r.get("trace_id", ""),
                json.dumps(r.get("attrs") or {}),
            )
            for r in records
        ],
    )
    conn.commit()


# Ordered loudest-first; an index into this is "at least this severe".
_SEVERITY_ORDER = ("FATAL", "ERROR", "WARNING", "INFO", "DEBUG", "TRACE")


def query_logs(
    run: str = "",
    node: str = "",
    level: str = "",
    contains: str = "",
    limit: int = 200,
) -> list[dict[str, Any]]:
    """The log search behind ``groom logs``, newest first.

    ``level`` is a floor, not an equality match — asking for WARNING and being
    shown warnings but no errors would be the opposite of useful.
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


def query_spans(
    run: str = "",
    node: str = "",
    status: str = "",
    slower_than: float | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """The /traces search: filter the spans table, newest first. ``slower_than``
    is a minimum duration in seconds. Raw SQL against groom.db remains the
    ad-hoc escape hatch; this covers the common fleet questions."""
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
    params.append(max(1, min(int(limit), 1000)))
    rows = _connection().execute(
        f"SELECT * FROM spans WHERE {' AND '.join(clauses)}"  # noqa: S608 - clauses are literals
        " ORDER BY start_ts DESC LIMIT ?",
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def run_summaries(limit: int = 50) -> list[dict[str, Any]]:
    """One row per run for the fleet/telemetry view: workflow, span window,
    span/error counts, and whether a root (run:*) span has landed (= the run
    ended; open runs have only node spans so far)."""
    rows = _connection().execute(
        "SELECT run_id, MAX(workflow) AS workflow, MAX(repo) AS repo,"
        " MIN(start_ts) AS first_ts, MAX(end_ts) AS last_ts,"
        " COUNT(*) AS span_count,"
        " SUM(CASE WHEN status = 'ERROR' THEN 1 ELSE 0 END) AS error_count,"
        " MAX(CASE WHEN name LIKE 'run:%' THEN 1 ELSE 0 END) AS finished"
        " FROM spans WHERE run_id != '' GROUP BY run_id"
        " ORDER BY last_ts DESC LIMIT ?",
        (max(1, min(int(limit), 500)),),
    ).fetchall()
    return [dict(row) for row in rows]


# The metrics that describe a run's LIVE state, as opposed to its history. Spans
# only export once they end, so for a run still in flight these are the whole
# picture: the trace of a hanging node does not exist yet and never will while it
# hangs.
_LIVE_METRICS = (
    "workhorse.run.heartbeat",
    "workhorse.node.elapsed_s",
    "workhorse.turn.idle_s",
    "workhorse.gas",
)

# How stale the last heartbeat may be before a run is presumed dead. Workhorse
# beats every ~10s, but the SDK's periodic reader only ships metrics every 60s by
# default, so anything under ~2 export intervals would flag healthy runs.
LIVE_AFTER_S = float(os.environ.get("GROOM_LIVE_AFTER_S", "180"))


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
    run_clause = ""
    if run:
        run_clause = "AND run_id = ?"
        params.append(run)
    rows = _connection().execute(
        # One row per (run, metric, attribute-set): the most recent point wins.
        f"""
        WITH latest AS (
            SELECT run_id, name, value, attrs_json, ts,
                   ROW_NUMBER() OVER (
                       PARTITION BY run_id, name ORDER BY ts DESC
                   ) AS rn
            FROM metrics
            WHERE name IN ({placeholders}) AND run_id != '' {run_clause}
        )
        SELECT run_id, name, value, attrs_json, ts FROM latest WHERE rn = 1
        """,  # noqa: S608 - placeholders/clause are literals, values are bound
        params,
    ).fetchall()

    runs: dict[str, dict[str, Any]] = {}
    for row in rows:
        entry = runs.setdefault(
            row["run_id"],
            {
                "run_id": row["run_id"], "workflow": "", "run_dir": "", "node": "",
                "node_elapsed_s": 0.0, "turn_idle_s": 0.0, "gas": None,
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
        elif row["name"] == "workhorse.turn.idle_s":
            entry["turn_idle_s"] = row["value"]
        elif row["name"] == "workhorse.gas":
            entry["gas"] = row["value"]

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


def prune(retention_days: float = RETENTION_DAYS, now: float | None = None) -> int:
    """Drop spans/metrics/logs older than the retention window; rows removed.

    Logs get their own, shorter window (``GROOM_LOG_RETENTION_DAYS``): they are
    the highest-volume table by a wide margin — one row per log line rather than
    one per node visit — so holding them for the span retention would let a few
    chatty week-long runs dominate the file.
    """
    stamp = now if now is not None else time.time()
    cutoff = stamp - retention_days * 86400
    conn = _connection()
    removed = conn.execute("DELETE FROM spans WHERE end_ts < ?", (cutoff,)).rowcount
    removed += conn.execute("DELETE FROM metrics WHERE ts < ?", (cutoff,)).rowcount
    removed += conn.execute(
        "DELETE FROM logs WHERE ts < ?", (stamp - LOG_RETENTION_DAYS * 86400,)
    ).rowcount
    conn.commit()
    return removed
