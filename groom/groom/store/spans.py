from __future__ import annotations

import json
import logging
import time
from typing import Any

from groom.store.connection import ACTIVE_WINDOW_S, read_connection, reading


logger = logging.getLogger(__name__)
_SEVERITY_ORDER = ("FATAL", "ERROR", "WARNING", "INFO", "DEBUG", "TRACE")


@reading
def query_logs(
    run: str = "",
    node: str = "",
    level: str = "",
    contains: str = "",
    limit: int = 200,
    before_ts: float | None = None,
    since_ts: float | None = None,
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
    if since_ts is not None:
        where.append("ts >= ?")
        params.append(float(since_ts))
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    conn = read_connection()
    rows = conn.execute(
        f"SELECT run_id, workflow, run_dir, node, logger, severity, body, ts, trace_id,"  # noqa: S608
        f" attrs_json, head, workspace, vcs, origin, branch, repositories"
        f" FROM logs {clause} ORDER BY ts DESC, rowid DESC LIMIT ?",
        (*params, limit),
    ).fetchall()
    return [
        {**dict(row), "attrs": json.loads(row["attrs_json"] or "{}")} for row in rows
    ]


_SPAN_COLUMNS = (
    "span_id, trace_id, parent_id, run_id, workflow, repo, branch, node, name,"
    " run_dir, start_ts, end_ts, status, attrs_json, head_start, head_end,"
    " workspace_start, workspace_end, vcs_start, vcs_end, origin_start, origin_end,"
    " branch_start, branch_end, repositories_start, repositories_end"
)


_RUN_SPAN_COLUMNS = (
    "span_id, trace_id, parent_id, run_id, workflow, repo, branch, node, name,"
    " run_dir, start_ts, end_ts, status, attrs_json, workspace_start, branch_start, branch_end"
)


@reading
def query_spans(
    run: str = "",
    node: str = "",
    status: str = "",
    slower_than: float | None = None,
    limit: int = 200,
    before_ts: float | None = None,
    since_ts: float | None = None,
) -> list[dict[str, Any]]:
    """Filter the spans table, newest first."""
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
        read_connection()
        .execute(
            f"SELECT {_SPAN_COLUMNS} FROM spans WHERE {' AND '.join(clauses)}"  # noqa: S608 - literals
            " ORDER BY start_ts DESC LIMIT ?",
            params,
        )
        .fetchall()
    )
    return [dict(row) for row in rows]


def older_than(
    rank: int, before: tuple[float, int, int] | None, ts: str, row: str
) -> tuple[str, list[Any]]:
    """The SQL condition keeping the rows of one record kind that sort after a cursor of time, kind rank and row id in the newest-first order."""
    if before is None:
        return "1=1", []
    when, ranked, ident = before
    if rank < ranked:
        return f"{ts} <= ?", [when]
    if rank > ranked:
        return f"{ts} < ?", [when]
    return f"({ts} < ? OR ({ts} = ? AND {row} < ?))", [when, when, ident]


@reading
def detail_metrics(
    run: str,
    limit: int = 60,
    before: tuple[float, int, int] | None = None,
    rank: int = 1,
) -> list[dict[str, Any]]:
    """Persisted metrics of one run, newest first, from a cursor of time, kind rank and row id."""
    clause, bound = older_than(rank, before, "ts", "rowid")
    rows = (
        read_connection()
        .execute(
            f"SELECT rowid AS id, name, ts, value, attrs_json FROM metrics"  # noqa: S608 - literals
            f" WHERE run_id = ? AND {clause} ORDER BY ts DESC, rowid DESC LIMIT ?",
            (run, *bound, limit),
        )
        .fetchall()
    )
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "ts": row["ts"],
            "value": row["value"],
            "attrs": json.loads(row["attrs_json"]),
        }
        for row in rows
    ]


@reading
def count_metrics(run: str) -> int:
    """How many metric samples one run stored."""
    return int(
        read_connection()
        .execute("SELECT COUNT(*) FROM metrics WHERE run_id = ?", (run,))
        .fetchone()[0]
    )


_TIMELINE_LEVELS = ("FATAL", "ERROR", "WARNING", "INFO")


@reading
def run_log_rows(
    run: str,
    limit: int = 200,
    before: tuple[float, int, int] | None = None,
    rank: int = 2,
    everything: bool = False,
) -> list[dict[str, Any]]:
    """One run's logs newest first, from a cursor of time, kind rank and row id. Without `everything` only INFO and above."""
    clause, bound = older_than(rank, before, "ts", "rowid")
    keep = (
        ""
        if everything
        else f" AND severity IN ({','.join('?' * len(_TIMELINE_LEVELS))})"
    )
    rows = (
        read_connection()
        .execute(
            f"SELECT rowid AS id, ts, severity, node, body FROM logs"  # noqa: S608 - literals
            f" WHERE run_id = ? AND {clause}{keep} ORDER BY ts DESC, rowid DESC LIMIT ?",
            (run, *bound, *([] if everything else _TIMELINE_LEVELS), limit),
        )
        .fetchall()
    )
    return [dict(row) for row in rows]


@reading
def count_logs(run: str, everything: bool = False) -> int:
    """How many logs one run stored, at INFO and above unless `everything`."""
    keep = (
        ""
        if everything
        else f" AND severity IN ({','.join('?' * len(_TIMELINE_LEVELS))})"
    )
    return int(
        read_connection()
        .execute(
            f"SELECT COUNT(*) FROM logs WHERE run_id = ?{keep}",  # noqa: S608 - literals
            (run, *([] if everything else _TIMELINE_LEVELS)),
        )
        .fetchone()[0]
    )


@reading
def detail_spans(run: str) -> list[dict[str, Any]]:
    """Compact span identities for an open pane's snapshot and idempotent updates."""
    rows = (
        read_connection()
        .execute(
            "SELECT span_id, node, name, start_ts, end_ts, status,"
            " json_extract(attrs_json, '$.\"workhorse.visit.slug\"') AS slug FROM spans"
            " WHERE run_id = ?",
            (run,),
        )
        .fetchall()
    )
    return [dict(row) for row in rows]


@reading
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
        read_connection()
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


@reading
def run_directories(run_id: str = "") -> list[dict[str, Any]]:
    """Every run telemetry has seen a directory for, or only `run_id`'s: run_id, run_dir, workflow."""
    return [
        dict(row)
        for row in read_connection().execute(
            "SELECT DISTINCT run_id, run_dir, workflow FROM spans"
            " WHERE run_dir != '' AND run_id != '' AND (? = '' OR run_id = ?)",
            (run_id, run_id),
        )
    ]
