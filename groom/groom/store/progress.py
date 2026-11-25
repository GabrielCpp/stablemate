from __future__ import annotations

import logging
import re
import statistics
from collections import defaultdict
from typing import Any

from groom.store.connection import read_connection, reading
from groom.store.costs import _duration


logger = logging.getLogger(__name__)
MIN_NORM_RUNS = 5


SUCCESS_TERMINAL = "terminal"


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


@reading
def node_norms(workflow: str, node: str) -> dict[str, dict[str, Any]]:
    """The median length of a turn and of a deterministic step at one node, across successful runs of the same workflow.

    A run is one trace, because a run id repeats across executions. It is successful when its root span ended with ``workhorse.terminal`` equal to ``terminal``. A node that ran agent turns in a run contributes those turns and no step from that run.
    """
    empty: dict[str, Any] = {"median_s": None, "runs": 0}
    if not workflow or not node:
        return {"turn": dict(empty), "step": dict(empty), "node": {"kind": None}}
    rows = (
        read_connection()
        .execute(
            f"SELECT trace_id, name, COALESCE({_duration} / 1000.0, end_ts - start_ts) AS seconds"  # noqa: S608 — _duration is a literal; every value is bound
            " FROM spans WHERE node = ? AND workflow = ?"
            " AND (name = 'agent_turn' OR (name = ? AND json_extract(attrs_json, '$.\"workhorse.span_kind\"') IS NULL))"
            " AND trace_id IN (SELECT trace_id FROM spans WHERE node = ?"
            " AND json_extract(attrs_json, '$.\"workhorse.terminal\"') = ?)",
            (node, workflow, node, f"run:{workflow}", SUCCESS_TERMINAL),
        )
        .fetchall()
    )
    turns: dict[str, list[float]] = defaultdict(list)
    steps: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        (turns if row["name"] == "agent_turn" else steps)[row["trace_id"]].append(
            row["seconds"]
        )
    for trace_id in turns:
        steps.pop(trace_id, None)
    found: dict[str, dict[str, Any]] = {
        kind: {
            "median_s": _median([s for run in samples.values() for s in run]),
            "runs": len(samples),
        }
        for kind, samples in (("turn", turns), ("step", steps))
    }
    found["node"] = {"kind": _node_kind(workflow, node)}
    return found


def _node_kind(workflow: str, node: str) -> str | None:
    """What a node is, from any run of the workflow: ``agent`` once it has run a turn, ``step`` once it has run only deterministic work, None before any finished visit."""
    names = {
        row["name"]
        for row in read_connection().execute(
            "SELECT DISTINCT name FROM spans WHERE node = ? AND workflow = ?"
            " AND (name = 'agent_turn' OR (name = ? AND json_extract(attrs_json, '$.\"workhorse.span_kind\"') IS NULL))",
            (node, workflow, node),
        )
    }
    if "agent_turn" in names:
        return "agent"
    return "step" if names else None


_PROGRESS = re.compile(r"^(\d+)/(\d+)$")


ACTIVE_TIME_KEYS = ("agent", "deterministic", "infra")


def active_seconds(time_s: dict[str, Any]) -> float:
    """The time a run was working: agent turns, deterministic steps and infrastructure, without waits, resume gaps or unclassified time."""
    return sum(float(time_s[key]) for key in ACTIVE_TIME_KEYS)


def parse_progress(value: Any) -> tuple[int, int] | None:
    """``done/total`` from a workflow's ``progress`` label, or None for prose and for a total of zero."""
    match = _PROGRESS.match(value.strip()) if isinstance(value, str) else None
    if match is None:
        return None
    done, total = int(match.group(1)), int(match.group(2))
    return (done, total) if total > 0 else None


@reading
def latest_progress(run: str) -> tuple[int, int] | None:
    """The item count on the run's most recently ended span that reports one."""
    cursor = read_connection().execute(
        "SELECT json_extract(attrs_json, '$.progress') AS progress FROM spans"
        " WHERE run_id = ? AND json_extract(attrs_json, '$.progress') IS NOT NULL"
        " ORDER BY end_ts DESC, span_id DESC",
        (run,),
    )
    for row in cursor:
        if (found := parse_progress(row["progress"])) is not None:
            return found
    return None
