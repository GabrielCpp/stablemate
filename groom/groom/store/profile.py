from __future__ import annotations

import json
import logging
import sqlite3
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from groom import memory, problems
from groom.flows import build_flows

from groom.store.connection import read_connection, reading
from groom.store.costs import (
    _cache_read,
    _cache_write,
    _charge,
    _charges,
    _duration,
    _input,
    _output,
)
from groom.store.profile_parts import (
    _kept_attr,
    _profile_groups,
    _profile_time_partition,
    _profile_turn_summary,
    _profile_verdict_decisions,
)
from groom.store.progress import active_seconds
from groom.store.spans import _RUN_SPAN_COLUMNS


logger = logging.getLogger(__name__)


def _run_span(row: sqlite3.Row, keep: Callable[[str], bool]) -> dict[str, Any]:
    """One span row as a dict, with the attributes ``keep`` accepts."""
    span = {key: row[key] for key in row.keys() if key != "attrs_json"}  # noqa: SIM118
    span["attrs"] = {
        k: v for k, v in json.loads(row["attrs_json"] or "{}").items() if keep(k)
    }
    return span


def _run_spans(
    run: str, keep: Callable[[str], bool] = _kept_attr
) -> list[dict[str, Any]]:
    cursor = read_connection().execute(
        f"{_charges('run_id = ?')}SELECT {_RUN_SPAN_COLUMNS}, {_duration} AS profile_duration_ms,"  # noqa: S608
        f" {_charge} AS profile_cost_usd, {_output} AS profile_output_tokens,"
        f" {_input} AS profile_input_tokens, {_cache_read} AS profile_cache_read_tokens,"
        f" {_cache_write} AS profile_cache_write_tokens,"
        " est_cost_usd, spans.rowid AS row_id, resume_generation"
        " FROM spans LEFT JOIN charges USING (span_id)"
        " WHERE run_id = ? ORDER BY start_ts",
        (run, run),
    )
    spans = [_run_span(row, keep) for row in cursor]
    memory.note_read(len(spans))
    return spans


@reading
def run_turn_spans(run: str) -> list[dict[str, Any]]:
    """Every span of one run, oldest first, with the cost, token and duration figures the profile computes."""
    return _run_spans(run) if run else []


@reading
def run_flows(run: str) -> dict[str, Any]:
    """One run's finished work as flow, state and node rows, with the totals the rows add up to."""
    spans = _run_spans(run) if run else []
    turns = [span for span in spans if span["name"] == "agent_turn"]
    rows = build_flows(spans)
    finished = sum(
        1
        for span in spans
        if span["name"] == "agent_turn"
        or (
            not span["attrs"].get("workhorse.span_kind")
            and not span["name"].startswith("run:")
        )
    )
    return {
        "flows": rows,
        "standing": problems.standing(spans),
        "finished_spans": finished,
        "time_s": sum(row["time_s"] for row in rows),
        "last_turn_end_ts": max((turn["end_ts"] for turn in turns), default=None),
        "work": _profile_turn_summary(turns),
    }


def _profile_models(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for turn in turns:
        name = str(turn["attrs"].get("model") or "") or "(no model recorded)"
        row = found.setdefault(
            name,
            {
                "model": name,
                "turns": 0,
                "cost_turns": 0,
                "cost_usd": None,
                "output_tokens": 0,
                "input_tokens": 0,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
            },
        )
        row["turns"] += 1
        if turn["profile_cost_usd"] is not None:
            row["cost_turns"] += 1
            row["cost_usd"] = (row["cost_usd"] or 0.0) + float(turn["profile_cost_usd"])
        row["output_tokens"] += turn["profile_output_tokens"] or 0
        row["input_tokens"] += turn["profile_input_tokens"] or 0
        row["cache_read_tokens"] += turn["profile_cache_read_tokens"] or 0
        row["cache_write_tokens"] += turn["profile_cache_write_tokens"] or 0
    for row in found.values():
        context = (
            row["input_tokens"] + row["cache_read_tokens"] + row["cache_write_tokens"]
        )
        row["cache_read_share"] = (
            row["cache_read_tokens"] / context if context else None
        )
    return sorted(
        found.values(),
        key=lambda row: (
            row["cost_usd"] is None,
            -(row["cost_usd"] or 0.0),
            -row["turns"],
            row["model"],
        ),
    )


def _session_ending(spans: list[dict[str, Any]]) -> dict[str, str] | None:
    roots = [
        span
        for span in spans
        if span["name"].startswith("run:") and span["attrs"].get("workhorse.terminal")
    ]
    if not roots:
        return None
    attrs = max(roots, key=lambda span: span["end_ts"])["attrs"]
    return {
        "terminal": str(attrs["workhorse.terminal"]),
        "error_class": str(attrs.get("error.class") or ""),
        "error_kind": str(attrs.get("error.kind") or ""),
        "message": str(attrs.get("status_message") or ""),
    }


def _profile_sessions(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per session the ``sessions`` count counts: when it started, how long it worked, the gap before the next one and how its root span ended."""
    by_generation: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for span in spans:
        if isinstance(span.get("resume_generation"), int):
            by_generation[span["resume_generation"]].append(span)
    groups = [by_generation[key] for key in sorted(by_generation)] or (
        [spans] if spans else []
    )
    bounds = sorted(
        (
            (min(s["start_ts"] for s in group), max(s["end_ts"] for s in group), group)
            for group in groups
        ),
        key=lambda bound: bound[0],
    )
    rows: list[dict[str, Any]] = []
    for index, (start, end, group) in enumerate(bounds):
        following = bounds[index + 1][0] if index + 1 < len(bounds) else None
        rows.append(
            {
                "start_ts": start,
                "end_ts": end,
                "active_s": active_seconds(_profile_time_partition(group, start, end)),
                "gap_s": None if following is None else max(0.0, following - end),
                "ended": _session_ending(group),
            }
        )
    return rows


def _latest(spans: list[dict[str, Any]], *keys: str) -> str:
    for span in reversed(spans):
        for key in keys:
            if span.get(key):
                return str(span[key])
    return ""


_ROW_ATTRS = frozenset(
    {
        "workhorse.span_kind",
        "workhorse.wait_kind",
        "workhorse.depth",
        "workhorse.flow",
        "workhorse.state",
    }
)


def _observed_bounds(
    run: str, spans: list[dict[str, Any]]
) -> tuple[float, float] | None:
    """The first start and last end over a run's spans and metric samples, or None when it has neither."""
    metric_bounds = (
        read_connection()
        .execute(
            "SELECT MIN(ts) AS first_ts, MAX(ts) AS last_ts FROM metrics WHERE run_id = ?",
            (run,),
        )
        .fetchone()
    )
    metric_start = metric_bounds["first_ts"] if metric_bounds else None
    metric_end = metric_bounds["last_ts"] if metric_bounds else None
    if not spans and metric_start is None:
        return None

    starts = [span["start_ts"] for span in spans]
    ends = [span["end_ts"] for span in spans]
    if metric_start is not None:
        starts.append(metric_start)
        ends.append(metric_end)
    return min(starts), max(ends)


@reading
def run_row_profile(run: str) -> dict[str, Any] | None:
    """The part of a run's profile its row shows, the time partition and the flows, from a read that keeps only the attributes those need."""
    if not run:
        return None
    spans = _run_spans(run, _ROW_ATTRS.__contains__)
    bounds = _observed_bounds(run, spans)
    if bounds is None:
        return None
    return {
        "time_s": _profile_time_partition(spans, *bounds),
        "flows": build_flows(spans),
    }


@reading
def run_profile(run: str) -> dict[str, Any] | None:
    """Partition one run's retained wall time and aggregate its agent rework."""
    if not run:
        return None
    spans = _run_spans(run)
    bounds = _observed_bounds(run, spans)
    if bounds is None:
        return None
    start_ts, end_ts = bounds
    turns = [span for span in spans if span["name"] == "agent_turn"]
    return {
        "run_id": run,
        "workflow": next((span["workflow"] for span in spans if span["workflow"]), ""),
        "observed_start_ts": start_ts,
        "observed_end_ts": end_ts,
        "time_s": _profile_time_partition(spans, start_ts, end_ts),
        "sessions": problems.sessions(spans),
        "session_rows": _profile_sessions(spans),
        "models": _profile_models(turns),
        "facts": {
            "branch": _latest(spans, "branch", "branch_end", "branch_start"),
            "run_dir": _latest(spans, "run_dir"),
        },
        "work": _profile_turn_summary(turns),
        "attempt_groups": _profile_groups(turns, verdicts=False),
        "verdict_groups": _profile_groups(turns, verdicts=True),
        "verdict_decisions": _profile_verdict_decisions(spans),
        "flows": build_flows(spans),
    }
