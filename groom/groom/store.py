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
"""

_conn: sqlite3.Connection | None = None


def db_path() -> Path:
    """``$GROOM_DB`` (tests point it at a temp file), else the platform data
    dir — read per call so a test's env var takes effect without reimport."""
    env = os.environ.get("GROOM_DB")
    if env:
        return Path(env)
    return Path(user_data_dir("groom")) / "groom.db"


def _connection() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        path = db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.executescript(_SCHEMA)
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
        " repo, branch, node, name, start_ts, end_ts, status, attrs_json)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                s["span_id"], s["trace_id"], s.get("parent_id", ""), s.get("run_id", ""),
                s.get("workflow", ""), s.get("repo", ""), s.get("branch", ""),
                s.get("node", ""), s.get("name", ""), s.get("start_ts", 0.0),
                s.get("end_ts", 0.0), s.get("status", "UNSET"),
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


def prune(retention_days: float = RETENTION_DAYS, now: float | None = None) -> int:
    """Drop spans/metrics older than the retention window; returns rows removed."""
    cutoff = (now if now is not None else time.time()) - retention_days * 86400
    conn = _connection()
    removed = conn.execute("DELETE FROM spans WHERE end_ts < ?", (cutoff,)).rowcount
    removed += conn.execute("DELETE FROM metrics WHERE ts < ?", (cutoff,)).rowcount
    conn.commit()
    return removed
