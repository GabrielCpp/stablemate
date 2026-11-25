from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass
from typing import Any

from groom.models import (
    LIVENESS_METRICS,
    UNARCHIVED_DELETABLE_METRICS,
)

from groom.store.connection import (
    RETENTION_DAYS,
    STORE,
    _connection,
    read_connection,
    reading,
    resilient,
)
from groom.store.testruns import _test_run_ids


logger = logging.getLogger(__name__)
_PRUNE_CHUNK = 50_000


_NEVER_ARCHIVED_METRICS = UNARCHIVED_DELETABLE_METRICS + LIVENESS_METRICS


@resilient
def _delete_chunk(table: str, clause: str, params: tuple[Any, ...]) -> int:
    """One ``_PRUNE_CHUNK``-row DELETE, in its own transaction; rows removed."""
    with STORE.writing() as conn:
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


@reading
def _expired_run_ids(cutoff: float) -> set[str]:
    """Run ids still holding at least one row older than ``cutoff``."""
    conn = read_connection()
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
    STORE.note_prune()
    return removed


@dataclass(frozen=True, slots=True)
class RecentRun:
    """One row of :func:`recent_runs` — what ``groom recent`` shows."""

    run_id: str
    workflow: str = ""
    max_ts: float = 0.0
    spans: int = 0
    ended_ts: float = 0.0

    @property
    def ended(self) -> bool:
        """The run's ``run:*`` span closed, and nothing reached the store after it."""
        return bool(self.ended_ts) and self.ended_ts >= self.max_ts


def _checkpoint() -> None:
    """Fold the write-ahead log back into the database file, and truncate it."""
    try:
        with STORE.lock:
            row = _connection().execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    except sqlite3.Error as exc:
        logger.warning("groom: WAL checkpoint declined: %s", exc)
        return
    busy = int(row[0]) if row else 0
    STORE.note_checkpoint(busy)
    if busy:
        logger.info(
            "groom: WAL checkpoint found a reader in the way; %s frames left in place",
            row[1] if row else "?",
        )


@resilient
def checkpoint() -> None:
    """:func:`_checkpoint`, healing the connection if the PRAGMA itself cannot run."""
    _checkpoint()
