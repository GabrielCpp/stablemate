"""The median a finished run is judged against: cost per finished item and time per visit of a node, over the successful runs of its workflow in the stored summaries."""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from typing import Any

from groom import store
from groom.store import read_connection, reading

MIN_RUNS = store.MIN_NORM_RUNS
SUCCESS = "success"

_ENDED_SUCCESS = "state = 'ready' AND ended_ts IS NOT NULL AND ending = 'success'"


def _each(spent: float | None, done: int | None) -> float | None:
    return spent / done if spent is not None and done else None


@reading
def per_item_costs(alive: set[str]) -> dict[str, dict[str, float]]:
    """Per workflow, the cost per finished item of every successful run that reported a price and finished an item. A run that reports no cost has only an estimate and stays out."""
    rows = read_connection().execute(
        f"SELECT run_id, workflow, cost_usd, items_done FROM run_summary WHERE {_ENDED_SUCCESS}"  # noqa: S608 - literals only
        " AND cost_usd IS NOT NULL AND priced_turns > 0 AND items_done > 0"
    )
    found: dict[str, dict[str, float]] = defaultdict(dict)
    for row in rows:
        if row["run_id"] not in alive:
            found[row["workflow"]][row["run_id"]] = row["cost_usd"] / row["items_done"]
    return dict(found)


def median_of_others(costs: dict[str, float], run_id: str) -> tuple[float | None, int]:
    """The median cost per item of the runs other than this one, and how many there are."""
    others = [cost for other, cost in costs.items() if other != run_id]
    return (statistics.median(others) if others else None), len(others)


def per_workflow(pool: dict[str, dict[str, float]]) -> dict[str, dict[str, Any]]:
    """What the totals show with a workflow chosen: the median over every successful run and how many stand behind it."""
    return {
        workflow: {"usd": statistics.median(costs.values()), "runs": len(costs)}
        for workflow, costs in pool.items()
    }


def compare(item: dict[str, Any], costs: dict[str, float]) -> dict[str, Any]:
    """One run's cost per item and, for a successful run with a price, its signed percent against the median of the other successful runs of the workflow. Under five such runs there is no percent."""
    done = item["items_done"]
    each = _each(item["cost_usd"], done)
    found: dict[str, Any] = {
        "per_item_usd": each,
        "per_item_est_usd": _each(item["est_usd"], done) if each is None else None,
        "vs_pct": None,
        "vs_median_usd": None,
        "vs_runs": None,
    }
    if each is None or item["ending"] != SUCCESS:
        return found
    median, runs = median_of_others(costs, item["run_id"])
    found["vs_runs"] = runs
    if runs >= MIN_RUNS and median:
        found["vs_median_usd"] = median
        found["vs_pct"] = (each - median) / median * 100
    return found


@reading
def _node_means(workflow: str, run_id: str) -> dict[str, list[float]]:
    rows = read_connection().execute(
        f"SELECT nodes_json FROM run_summary WHERE {_ENDED_SUCCESS} AND workflow = ? AND run_id != ?",  # noqa: S608 - literals only
        (workflow, run_id),
    )
    means: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        for node in json.loads(row["nodes_json"]):
            if node["turns"] and node["samples"]:
                means[node["node"]].append(node["time_s"] / node["samples"])
    return means


def node_readings(workflow: str, run_id: str, nodes: list[dict[str, Any]], compared: bool) -> dict[str, dict[str, Any] | None]:
    """Each agent node's median time per visit across the other successful runs of the workflow, from their stored summaries. A run that did not succeed, and a step, reads none."""
    means = _node_means(workflow, run_id) if compared else {}
    found: dict[str, dict[str, Any] | None] = {}
    for row in nodes:
        samples = means.get(row["node"], [])
        enough = len(samples) >= MIN_RUNS
        found[row["node"]] = (
            {"median_s": statistics.median(samples) if enough else None, "runs": len(samples)}
            if compared and row["kind"] == "agent"
            else None
        )
    return found
