from __future__ import annotations

import json
from typing import Any

from groom import archive, figures, flows, history, medians, norms, store


def outcome(item: dict[str, Any], progress: tuple[int, int] | None) -> str:
    if progress is None or item["done"] is None:
        return "unknown"
    return "done" if progress[0] > item["done"] else "uncounted"


def _items(
    rows: list[dict[str, Any]],
    progress: tuple[int, int] | None,
    tree: list[dict[str, Any]],
    time_s: float,
) -> dict[str, Any] | None:
    if not rows:
        return None
    priced = [row["cost_usd"] for row in tree if row["cost_usd"] is not None]
    spent = [row["cost_usd"] for row in rows if row["cost_usd"] is not None]
    cost_usd = sum(priced) if priced else None
    item_cost = sum(spent) if spent else None
    outside_cost = None
    if cost_usd is not None:
        outside_cost = max(0.0, cost_usd - (item_cost or 0.0))
    tokens = sum(row["output_tokens"] for row in tree)
    item_tokens = sum(row["output_tokens"] for row in rows)
    item_time = sum(row["seconds"] for row in rows)
    return {
        "rows": [{**row, "outcome": outcome(row, progress)} for row in rows],
        "outside": {
            "time_s": max(0.0, time_s - item_time),
            "cost_usd": outside_cost,
            "output_tokens": max(0, tokens - item_tokens),
        },
        "total": {"time_s": time_s, "cost_usd": cost_usd, "output_tokens": tokens},
    }


def run_overview(run_id: str) -> dict[str, Any]:
    costs, profile, progress = figures.read(run_id)
    with archive.run_source(run_id):
        result = store.run_flows(run_id)
        work = store.run_work_items(run_id)
    tiles = figures.tile_figures(costs, profile, progress)
    nodes = flows.node_breakdown(result["flows"])
    workflow = profile["workflow"] if profile else ""
    compare = history.comparison(run_id)
    if compare is None:
        readings = norms.for_nodes(workflow, {row["node"]: row["kind"] for row in nodes})
    else:
        readings = medians.node_readings(compare["workflow"], run_id, nodes, compare["ending"] == medians.SUCCESS)
    for row in nodes:
        row["norm"] = readings[row["node"]]
    return {
        "finished": tiles["finished"],
        "run_id": run_id,
        "cost": costs,
        "figures": tiles,
        "standing": result["standing"],
        "flows": result["flows"],
        "nodes": nodes,
        "compare": compare,
        "norm_runs": max((row["norm"]["runs"] for row in nodes if row["norm"]), default=0),
        "items": _items(work, progress, result["flows"], result["time_s"]),
        "time_s": result["time_s"],
        "clock": profile["time_s"] if profile else None,
        "models": profile["models"] if profile else [],
        "sessions": profile["session_rows"] if profile else [],
        "facts": {
            "started_ts": profile["observed_start_ts"] if profile else None,
            **(profile["facts"] if profile else {"branch": "", "run_dir": ""}),
        },
        "as_of_ts": result["last_turn_end_ts"],
    }


def stored_overview(row: dict[str, Any], compare: dict[str, Any] | None) -> dict[str, Any]:
    """What an archive whose files are gone still says, read from its stored summary: the tiles and the facts, with no breakdown, no clock and no sessions' detail."""
    ready = row["state"] == history.READY
    priced = row["cost_usd"] is not None and row["priced_turns"] > 0
    return {
        "archive": "gone",
        "finished": ready,
        "run_id": row["run_id"],
        "figures": {
            "reports_cost": priced,
            "cost_usd": row["cost_usd"] if priced else None,
            "est_usd": row["est_usd"],
            "turns": row["turns"],
            "priced_turns": row["priced_turns"],
            "active_s": row["active_s"],
            "wall_s": row["wall_s"],
            "items_done": row["items_done"],
            "items_total": row["items_total"],
            "backends": [],
        },
        "gates": row["gates"],
        "problems": row["problems"],
        "compare": compare,
        "standing": {"retries": sum(node["retries"] for node in json.loads(row["nodes_json"])), "gates": row["gates"], "problems": row["problems"]},
        "facts": {"started_ts": None, "branch": row["branch"], "run_dir": ""},
    }
