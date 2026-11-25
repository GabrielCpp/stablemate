from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from groom.store.connection import read_connection, reading
from groom.store.costs import _charge, _charges, _cost, _duration, _output
from groom.span_views import view
from groom.store.progress import parse_progress
from groom.store.run_cache import run_spans


logger = logging.getLogger(__name__)
_LOOP_VERDICTS = (
    (0.8, "converged"),
    (0.5, "loose"),
    (0.3, "churning"),
    (0.0, "thrashing"),
)


MIN_LOOP_WORK_ITEMS = 3


@dataclass(frozen=True, slots=True)
class Lap:
    """One turn of a loop, as the three numbers ranking it needs. A `retry` ended on an error and the runner sent the same lap again."""

    cost: float | None
    suspect_zero: bool
    est: float | None
    seconds: float = 0.0
    output_tokens: int = 0
    start_ts: float = 0.0
    retry: bool = False


def _node_laps(
    run: str = "", workflow: str = "", since_ts: float | None = None
) -> dict[str, dict[tuple[str, str], list[Lap]]]:
    """Every agent turn that carries a work item, grouped by node and then by (run, work item), in start order."""
    clauses = [
        "name = 'agent_turn'",
        "json_extract(attrs_json, '$.work_id') IS NOT NULL",
    ]
    params: list[Any] = []
    if run:
        clauses.append("run_id = ?")
        params.append(run)
    if workflow:
        clauses.append("workflow = ?")
        params.append(workflow)
    scope = " AND ".join(clauses[2:]) or "1=1"
    scope_params = list(params)
    if since_ts is not None:
        clauses.append("start_ts >= ?")
        params.append(float(since_ts))
    rows = (
        read_connection()
        .execute(
            f"{_charges(scope)}SELECT node, run_id,"  # noqa: S608 — clauses are literals; every value is bound
            " json_extract(attrs_json, '$.work_id') AS work_id,"
            f" {_charge} AS cost_usd, {_cost} = 0 AND COALESCE({_output}, 0) > 0 AS suspect_zero,"
            " est_cost_usd, start_ts,"
            " json_extract(attrs_json, '$.\"error.kind\"') IS NOT NULL AS retry,"
            f" COALESCE({_duration} / 1000.0, end_ts - start_ts) AS seconds,"
            f" COALESCE({_output}, 0) AS output_tokens"
            f" FROM spans LEFT JOIN charges USING (span_id) WHERE {' AND '.join(clauses)}"
            " ORDER BY start_ts, end_ts, spans.rowid",
            [*scope_params, *params],
        )
        .fetchall()
    )

    laps: dict[str, dict[tuple[str, str], list[Lap]]] = {}
    for row in rows:
        item = (row["run_id"], str(row["work_id"]))
        lap = Lap(
            row["cost_usd"],
            bool(row["suspect_zero"]),
            row["est_cost_usd"],
            float(row["seconds"]),
            int(row["output_tokens"]),
            float(row["start_ts"]),
            bool(row["retry"]),
        )
        laps.setdefault(row["node"], {}).setdefault(item, []).append(lap)
    return laps


@reading
def loop_convergence(
    run: str = "",
    workflow: str = "",
    min_work_items: int = MIN_LOOP_WORK_ITEMS,
    since_ts: float | None = None,
) -> list[dict[str, Any]]:
    """Per-node lap distributions: which review→rework loops converge, and what the ones that don't are costing."""
    laps = _node_laps(run, workflow, since_ts)
    report = [
        row
        for node, items in laps.items()
        if (row := _loop_row(node, items)) is not None
    ]
    report = [row for row in report if row["work_items"] >= min_work_items]
    report.sort(
        key=lambda row: (-(row["excess_cost_usd"] or 0.0), -row["excess_turns"])
    )
    return report


@reading
def run_work_items(run: str) -> list[dict[str, Any]]:
    """One run's work items in the order they started, from the same agent turns ``groom loops`` counts laps over.

    ``done`` is the highest item count the item's own spans reported, so a caller can tell whether the run's count moved past it.
    """
    return view(run_spans(run), "run_work_items", lambda: _work_items(run))


def _work_items(run: str) -> list[dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    for node, by_item in _node_laps(run=run).items():
        for (_, work_id), laps in by_item.items():
            item = items.setdefault(
                work_id,
                {
                    "work_id": work_id,
                    "first_ts": laps[0].start_ts,
                    "last_ts": laps[0].start_ts,
                    "turns": 0,
                    "seconds": 0.0,
                    "output_tokens": 0,
                    "costs": [],
                    "nodes": {},
                },
            )
            item["first_ts"] = min(item["first_ts"], laps[0].start_ts)
            item["last_ts"] = max(item["last_ts"], laps[-1].start_ts)
            item["turns"] += len(laps)
            item["seconds"] += sum(lap.seconds for lap in laps)
            item["output_tokens"] += sum(lap.output_tokens for lap in laps)
            item["costs"] += [lap.cost for lap in laps if lap.cost is not None]
            item["nodes"][node] = len(laps)
    reported = read_connection().execute(
        "SELECT json_extract(attrs_json, '$.work_id') AS work_id,"
        " json_extract(attrs_json, '$.progress') AS progress FROM spans"
        " WHERE run_id = ? AND json_extract(attrs_json, '$.work_id') IS NOT NULL"
        " AND json_extract(attrs_json, '$.progress') IS NOT NULL",
        (run,),
    )
    done: dict[str, int] = {}
    for row in reported:
        if (found := parse_progress(row["progress"])) is not None:
            key = str(row["work_id"])
            done[key] = max(done.get(key, 0), found[0])
    rows = []
    for item in sorted(
        items.values(), key=lambda row: (row["first_ts"], row["work_id"])
    ):
        costs = item.pop("costs")
        rows.append(
            {
                **item,
                "passes": max(item["nodes"].values()),
                "cost_turns": len(costs),
                "cost_usd": sum(costs) if costs else None,
                "done": done.get(item["work_id"]),
            }
        )
    return rows


def _loop_row(
    node: str, turns_of: dict[tuple[str, str], list[Lap]]
) -> dict[str, Any] | None:
    """A node's lap distribution, or None when no turn of it ran to an answer. A turn that ended on an error is a retry and no lap."""
    retries = sum(1 for laps in turns_of.values() for lap in laps if lap.retry)
    items = {
        item: kept
        for item, laps in turns_of.items()
        if (kept := [lap for lap in laps if not lap.retry])
    }
    if not items:
        return None
    counts = sorted(len(laps) for laps in items.values())
    turns, work_items = sum(counts), len(counts)
    exit_rate = work_items / turns
    peak = counts[-1]
    every = [lap for laps in items.values() for lap in laps]
    priced = [lap.cost for lap in every if lap.cost is not None]
    estimated = [lap.est for lap in every if lap.est is not None]
    excess = [
        lap.cost for laps in items.values() for lap in laps[1:] if lap.cost is not None
    ]
    excess_est = [
        lap.est for laps in items.values() for lap in laps[1:] if lap.est is not None
    ]
    return {
        "node": node,
        "work_items": work_items,
        "turns": turns,
        "priced_turns": len(priced),
        "est_turns": len(estimated),
        "zero_cost_turns": sum(1 for lap in every if lap.suspect_zero),
        "excess_turns": turns - work_items,
        "retries": retries,
        "exit_rate": exit_rate,
        "mean_laps": turns / work_items,
        "median_laps": counts[work_items // 2],
        "max_laps": peak,
        "at_max": sum(1 for count in counts if count == peak),
        "share_ge3": sum(1 for count in counts if count >= 3) / work_items,
        "cost_usd": sum(priced) if priced else None,
        "est_cost_usd": sum(estimated) if estimated else None,
        "excess_cost_usd": sum(excess) if excess else None,
        "excess_est_cost_usd": sum(excess_est) if excess_est else None,
        "verdict": next(name for floor, name in _LOOP_VERDICTS if exit_rate >= floor),
    }
