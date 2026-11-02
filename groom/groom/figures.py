from __future__ import annotations

from typing import Any

from groom import archive, store


def cost_totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    turns = sum(row["turns"] for row in rows)
    priced = sum(row["cost_turns"] or 0 for row in rows)
    usd = [row["cost_usd"] for row in rows if row["cost_usd"] is not None]
    estimates = [row["est_cost_usd"] for row in rows if row["est_cost_usd"] is not None]
    backends = sorted(
        {name for row in rows for name in (row["backends"] or "").split(",") if name}
    )
    return {
        "turns": turns,
        "priced_turns": priced,
        "reports_cost": priced > 0,
        "usd": sum(usd) if usd else None,
        "est_usd": sum(estimates) if estimates else None,
        "output_tokens": sum(row["output_tokens"] or 0 for row in rows),
        "backends": backends,
    }


def read(run_id: str) -> tuple[dict[str, Any], dict[str, Any] | None, tuple[int, int] | None]:
    """The cost totals, the profile and the item count of one run, from the store functions behind ``groom cost`` and ``groom profile``."""
    with archive.run_source(run_id):
        costs = cost_totals(store.node_costs(run_id, limit=1000))
        profile = store.run_profile(run_id)
        progress = store.latest_progress(run_id)
    return costs, profile, progress


def row_figures(costs: dict[str, Any], profile: dict[str, Any] | None, progress: tuple[int, int] | None) -> dict[str, Any]:
    return {
        "finished": bool(profile and profile["flows"]),
        "reports_cost": costs["reports_cost"],
        "cost_usd": costs["usd"],
        "turns": costs["turns"],
        "priced_turns": costs["priced_turns"],
        "active_s": store.active_seconds(profile["time_s"]) if profile else 0.0,
        "items_done": progress[0] if progress else None,
        "items_total": progress[1] if progress else None,
    }


def tile_figures(costs: dict[str, Any], profile: dict[str, Any] | None, progress: tuple[int, int] | None) -> dict[str, Any]:
    """The run row's figures plus what the Overview tiles add: the estimate, the wall time and the session count."""
    return {
        **row_figures(costs, profile, progress),
        "est_usd": costs["est_usd"],
        "backends": costs["backends"],
        "wall_s": profile["time_s"]["wall"] if profile else 0.0,
        "sessions": profile["sessions"] if profile else 0,
    }


def run_figures(run_id: str) -> dict[str, Any]:
    """The figures one run row shows, from the store functions behind ``groom cost`` and ``groom profile``."""
    return row_figures(*read(run_id))
