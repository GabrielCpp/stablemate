from __future__ import annotations

import logging
import re
import sqlite3
import tempfile
from typing import Any

from groom.store.connection import (
    STORE,
    _connection,
    _noop_on_empty,
    read_connection,
    reading,
    resilient,
)


logger = logging.getLogger(__name__)
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
    return any(
        run_dir.startswith(root)
        and _PY_TEMP_DIR.match(run_dir[len(root) :].split("/", 1)[0])
        for root in _temp_roots()
    )


@reading
def _test_run_ids() -> set[str]:
    """The run ids whose run dir says they were throwaway (:func:`is_scratch_run_dir`)."""
    conn = read_connection()
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


@reading
def test_run_ids() -> set[str]:
    """:func:`_test_run_ids`, with the store's heal-and-retry around it."""
    return _test_run_ids()


_PURGE_CHUNK = 500


@resilient
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
    with STORE.writing() as conn:
        sweep(conn)
    if vacuum and counts["runs"]:
        _vacuum()
    return counts


def _vacuum() -> None:
    with STORE.lock:
        _connection().execute("VACUUM")


@resilient
def vacuum() -> None:
    """Rewrite the database file so the space deleted rows held goes back to the disk."""
    _vacuum()


@_noop_on_empty(0)
@resilient
def insert_turns(rows: list[dict[str, Any]]) -> int:
    """Index archived turn records; how many rows the index gained or replaced."""
    if not rows:
        return 0
    with STORE.writing() as conn:
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
