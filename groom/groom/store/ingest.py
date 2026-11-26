from __future__ import annotations

import json
import logging
from typing import Any

from groom.models import (
    LIVENESS_METRICS,
)

from groom.store.connection import STORE, _noop_on_empty, reading, resilient
from groom.store.schema import _SPAN_VALUE_COLUMNS, _promoted


logger = logging.getLogger(__name__)


@_noop_on_empty(None)
@resilient
def insert_spans(spans: list[dict[str, Any]]) -> None:
    """Upsert decoded spans (see groom.otlp.parse_traces)."""
    if not spans:
        return
    with STORE.writing() as conn:
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


@resilient
def _write_metrics(points: list[dict[str, Any]]) -> None:
    """Store already-filtered, non-empty metric points."""
    with STORE.writing() as conn:
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
@resilient
def insert_logs(records: list[dict[str, Any]]) -> None:
    """Append decoded log records (see groom.otlp.parse_logs)."""
    if not records:
        return
    with STORE.writing() as conn:
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


@reading
def query_turns(
    run: str = "",
    node: str = "",
    session: str = "",
    workflow: str = "",
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Archived turns, newest visit last — a node's laps read top to bottom. The index of turns lives in ``groom.db`` and never in a frozen run's file, so a read redirected to an archive still asks the live database."""
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
    rows = STORE.read_connection().execute(
        "SELECT run_id, workflow, flow, node, session_id, generation, seq, ts, backend,"
        f" source, path, bytes, sha256, head FROM turns {where}"  # noqa: S608 - bound values
        " ORDER BY run_id, generation, seq LIMIT ?",
        params,
    )
    return [dict(row) for row in rows]
