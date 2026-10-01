"""The attendant sessions table: one row per attendance, its session ids and its outcome."""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

from groom.store import STORE, read_connection, reading, register_table, resilient

_ATTEND_DDL = """
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
"""

register_table("attend_sessions", _ATTEND_DDL)

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


@resilient
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
    with STORE.writing() as conn:
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


@resilient
def attend_append_session(job_id: str, session_id: str, pid: int | None = None) -> None:
    """Re-arm an existing row with a fresh session and pid, keeping its history."""
    with STORE.writing() as conn:
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


@resilient
def attend_finish(
    job_id: str,
    *,
    exit_code: int | None = None,
    released_state: str = "",
    ended_at: float | None = None,
) -> None:
    """Flip a row to ``completed``."""
    with STORE.writing() as conn:
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


@reading
def attend_running_for_run(run_id: str) -> dict[str, Any] | None:
    """The attendant currently on this run, if there is one."""
    row = (
        read_connection()
        .execute(
            "SELECT * FROM attend_sessions WHERE run_id = ? AND status = ?"
            " ORDER BY started_at DESC LIMIT 1",
            (run_id, ATTEND_RUNNING),
        )
        .fetchone()
    )
    return _attend_row(row) if row is not None else None


@reading
def attend_latest_for_run(run_id: str) -> dict[str, Any] | None:
    """The most recent attendant on this run, running or not — the pane's one link."""
    row = (
        read_connection()
        .execute(
            "SELECT * FROM attend_sessions WHERE run_id = ? ORDER BY started_at DESC LIMIT 1",
            (run_id,),
        )
        .fetchone()
    )
    return _attend_row(row) if row is not None else None


@reading
def attend_latest_by_run() -> dict[str, dict[str, Any]]:
    """The latest attendance per run, for the projection that links a blocked row to it."""
    rows = read_connection().execute(
        "SELECT * FROM attend_sessions ORDER BY started_at ASC"
    )
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        record = _attend_row(row)
        run_id = str(record.get("run_id") or "")
        if run_id:
            latest[run_id] = record
    return latest


@reading
def attend_recent(limit: int = 200) -> list[dict[str, Any]]:
    """The latest attendances, newest first."""
    rows = read_connection().execute(
        "SELECT * FROM attend_sessions ORDER BY started_at DESC LIMIT ?",
        (max(1, limit),),
    )
    return [_attend_row(row) for row in rows]


@reading
def attend_get(job_id: str) -> dict[str, Any] | None:
    row = (
        read_connection()
        .execute("SELECT * FROM attend_sessions WHERE job_id = ?", (job_id,))
        .fetchone()
    )
    return _attend_row(row) if row is not None else None


@reading
def attend_by_session(session_id: str) -> dict[str, Any] | None:
    """The attendance a session id belongs to — the pane routes on the session, not the job."""
    for row in read_connection().execute("SELECT * FROM attend_sessions"):
        record = _attend_row(row)
        if session_id in record["session_ids"]:
            return record
    return None


@reading
def attend_orphans() -> list[dict[str, Any]]:
    """Every row still claiming to be ``running`` — what boot recovery re-checks."""
    rows = read_connection().execute(
        "SELECT * FROM attend_sessions WHERE status = ? ORDER BY started_at ASC",
        (ATTEND_RUNNING,),
    )
    return [_attend_row(row) for row in rows]
