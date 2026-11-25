from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from groom.models import (
    ARCHIVED_METRICS,
)

from groom.store.connection import read_connection, reading
from groom.store.retention import _NEVER_ARCHIVED_METRICS, RecentRun, _chunked_delete
from groom.store.testruns import _test_run_ids


logger = logging.getLogger(__name__)


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


@reading
def run_bounds() -> dict[str, RunBounds]:
    """Per-run timestamp bounds, archivable row counts and identity."""
    conn = read_connection()
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


@reading
def recent_runs(limit: int = 10, workflow: str = "") -> list[RecentRun]:
    """Top runs ordered by most-recent activity, alive or dead."""
    conn = read_connection()

    sql_spans = (
        "SELECT run_id, MAX(MAX(start_ts, end_ts)) AS max_ts,"
        " MAX(workflow) AS workflow, COUNT(*) AS spans,"
        " MAX(CASE WHEN name LIKE 'run:%' THEN end_ts END) AS ended_ts"
        " FROM spans WHERE run_id != ''"
    )
    params: tuple = ()
    if workflow:
        sql_spans += " AND workflow = ?"
        params = (workflow,)
    sql_spans += " GROUP BY run_id ORDER BY max_ts DESC"
    if limit > 0:
        sql_spans += " LIMIT ?"
        params_spans = params + (limit * 4,)
    else:
        params_spans = params
    spans_rows = (
        conn.execute(sql_spans, params_spans)
        if params_spans
        else conn.execute(sql_spans)  # noqa: S608 - bound placeholders
    )

    spans_by_id: dict[str, tuple[float, str, int, float]] = {}
    for row in spans_rows:
        spans_by_id[row["run_id"]] = (
            float(row["max_ts"] or 0.0),
            row["workflow"] or "",
            int(row["spans"] or 0),
            float(row["ended_ts"] or 0.0),
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
    for run_id, (
        span_max_ts,
        workflow_value,
        span_count,
        ended_ts,
    ) in spans_by_id.items():
        metric_max_ts = metrics_by_id.get(run_id, 0.0)
        merged_max_ts = max(span_max_ts, metric_max_ts)
        out.append(
            RecentRun(
                run_id=run_id,
                workflow=workflow_value,
                max_ts=merged_max_ts,
                spans=span_count,
                ended_ts=ended_ts,
            )
        )
    out.sort(key=lambda row: row.max_ts, reverse=True)
    if limit > 0:
        out = out[:limit]
    return out


@reading
def unarchived_row_counts() -> dict[str, int]:
    """What is in the store that :func:`prune` may delete with no archive behind it."""
    conn = read_connection()
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


@reading
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
    rows = read_connection().execute(
        f"SELECT rowid AS _rowid, {ts_col} AS _ts, * FROM {table}"  # noqa: S608 - literal table/column
        f" WHERE run_id = ?{clause} AND ({ts_col} > ? OR ({ts_col} = ? AND rowid > ?))"
        f" ORDER BY {ts_col}, rowid LIMIT ?",
        params,
    )
    return [dict(row) for row in rows]


@reading
def has_run_rows(run_id: str) -> bool:
    """Does the store still hold a span, log or metric for ``run_id``?"""
    if not run_id:
        return False
    conn = read_connection()
    return any(
        conn.execute(
            f"SELECT 1 FROM {table} WHERE run_id = ? LIMIT 1", (run_id,)
        ).fetchone()  # noqa: S608
        for table in ("spans", "logs", "metrics")
    )


def delete_run_telemetry(run_id: str) -> int:
    """Drop every span, log and metric belonging to ``run_id``; rows removed."""
    if not run_id:
        return 0
    removed = 0
    for table in ("spans", "logs", "metrics"):
        removed += _chunked_delete(table, "run_id = ?", (run_id,))
    return removed


def delete_runs(run_ids: list[str]) -> int:
    """Drop every span, log, metric and turn index row of each run: telemetry first, so no harvest finds the run between the two; rows removed."""
    removed = 0
    for run_id in run_ids:
        if not run_id:
            continue
        removed += delete_run_telemetry(run_id)
        removed += _chunked_delete("turns", "run_id = ?", (run_id,))
    return removed


@reading
def turn_last_seen() -> dict[str, float]:
    """Per run, the start of the latest turn record the index holds."""
    rows = read_connection().execute(
        "SELECT run_id, MAX(ts) AS last FROM turns WHERE run_id != '' GROUP BY run_id"
    )
    return {row["run_id"]: float(row["last"] or 0.0) for row in rows}
