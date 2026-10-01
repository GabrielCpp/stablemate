"""The dispatch items table: each queued item's status, pid and exit."""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

from groom.store import STORE, read_connection, reading, register_table, resilient


_DISPATCH_DDL = """
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

register_table("dispatch_items", _DISPATCH_DDL)

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


@resilient
def dispatch_enqueue(
    item_id: str,
    *,
    queue: str,
    command: str,
    params: dict[str, Any] | None = None,
    enqueued_at: float | None = None,
) -> None:
    """Record a new item as ``pending``."""
    with STORE.writing() as conn:
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


@resilient
def dispatch_start(
    item_id: str,
    *,
    run_id: str = "",
    pid: int | None = None,
    started_at: float | None = None,
) -> None:
    """Flip a `pending` row to `running` — called by the thread launching the process."""
    with STORE.writing() as conn:
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


@resilient
def dispatch_finish(
    item_id: str,
    *,
    status: str,
    exit_code: int | None = None,
    ended_at: float | None = None,
) -> bool:
    """Flip a row to a terminal state (`done` / `failed` / `cancelled`) — but only if it is not terminal already."""
    with STORE.writing() as conn:
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


@resilient
def dispatch_cancel_pending(item_id: str) -> bool:
    """Cancel a still-`pending` item without ever spawning a process."""
    with STORE.writing() as conn:
        cursor = conn.execute(
            "UPDATE dispatch_items SET status = ?, ended_at = ?"
            " WHERE item_id = ? AND status = ?",
            (DISPATCH_CANCELLED, time.time(), item_id, DISPATCH_PENDING),
        )
        return cursor.rowcount > 0


@reading
def dispatch_get(item_id: str) -> dict[str, Any] | None:
    row = (
        read_connection()
        .execute("SELECT * FROM dispatch_items WHERE item_id = ?", (item_id,))
        .fetchone()
    )
    return _dispatch_row(row) if row is not None else None


@reading
def dispatch_list(queue: str, limit: int = 200) -> list[dict[str, Any]]:
    """Every item in this queue, newest first."""
    rows = read_connection().execute(
        "SELECT * FROM dispatch_items WHERE queue = ? ORDER BY enqueued_at DESC LIMIT ?",
        (queue, max(1, limit)),
    )
    return [_dispatch_row(row) for row in rows]


@reading
def dispatch_pending_for_queue(queue: str) -> list[dict[str, Any]]:
    """This queue's `pending` items, oldest first — the order they are launched in."""
    rows = read_connection().execute(
        "SELECT * FROM dispatch_items WHERE queue = ? AND status = ? ORDER BY enqueued_at ASC",
        (queue, DISPATCH_PENDING),
    )
    return [_dispatch_row(row) for row in rows]


@reading
def dispatch_running_for_queue(queue: str) -> list[dict[str, Any]]:
    """This queue's `running` items — its current occupancy."""
    rows = read_connection().execute(
        "SELECT * FROM dispatch_items WHERE queue = ? AND status = ? ORDER BY started_at ASC",
        (queue, DISPATCH_RUNNING),
    )
    return [_dispatch_row(row) for row in rows]


@reading
def dispatch_orphans() -> list[dict[str, Any]]:
    """Every row still claiming to be `running`, across every queue — what boot recovery re-checks (§3.5)."""
    rows = read_connection().execute(
        "SELECT * FROM dispatch_items WHERE status = ? ORDER BY started_at ASC",
        (DISPATCH_RUNNING,),
    )
    return [_dispatch_row(row) for row in rows]
