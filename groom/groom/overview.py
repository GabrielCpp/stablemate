from __future__ import annotations

from typing import Any

from groom import archive, figures, flows, norms, store


def _outcome(item: dict[str, Any], progress: tuple[int, int] | None) -> str:
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
        "rows": [{**row, "outcome": _outcome(row, progress)} for row in rows],
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
    readings = norms.for_nodes(workflow, {row["node"]: row["kind"] for row in nodes})
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
