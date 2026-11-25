from __future__ import annotations

import logging
import sqlite3
from collections import Counter
from typing import Any

from groom import prices

from groom.store.connection import STORE, read_connection, reading, resilient
from groom.store.schema import _estimated


logger = logging.getLogger(__name__)


def _promoted_or_attr(column: str, key: str) -> str:
    """The promoted column, falling back to the attribute it was promoted from."""
    return f"COALESCE({column}, json_extract(attrs_json, '$.\"{key}\"'))"


_cost = _promoted_or_attr("total_cost_usd", "total_cost_usd")


_duration = _promoted_or_attr("duration_ms", "duration_ms")


_output = _promoted_or_attr("output_tokens", "usage.output_tokens")


_input = _promoted_or_attr("input_tokens", "usage.input_tokens")


_cache_read = _promoted_or_attr("cache_read_tokens", "usage.cache_read_input_tokens")


_cache_write = _promoted_or_attr(
    "cache_creation_tokens", "usage.cache_creation_input_tokens"
)


SESSION_TOTAL_BACKENDS = ("claude",)


def _charges(scope: str) -> str:
    backends = ", ".join(f"'{backend}'" for backend in SESSION_TOTAL_BACKENDS)
    return (
        "WITH charges AS (SELECT span_id,"  # noqa: S608 — scope is a literal clause
        " CASE WHEN prior IS NULL OR reported < prior THEN reported"
        " ELSE reported - prior END AS charge_usd FROM ("
        " SELECT span_id, reported, LAG(reported) OVER ("
        " PARTITION BY run_id, session ORDER BY start_ts, end_ts, span_id) AS prior FROM ("
        f" SELECT span_id, run_id, start_ts, end_ts, {_cost} AS reported,"
        " json_extract(attrs_json, '$.\"session.id\"') AS session FROM spans"
        " WHERE name = 'agent_turn'"
        f" AND json_extract(attrs_json, '$.backend') IN ({backends}) AND {scope})"
        " WHERE session IS NOT NULL AND reported IS NOT NULL)) "
    )


_idle = (
    "json_extract(attrs_json, '$.backend') IN ("
    + ", ".join(f"'{backend}'" for backend in SESSION_TOTAL_BACKENDS)
    + ") AND "
    + " AND ".join(
        f"COALESCE({tokens}, -1) = 0"
        for tokens in (_input, _output, _cache_read, _cache_write)
    )
)


_charge = f"CASE WHEN {_idle} THEN 0.0 ELSE COALESCE(charges.charge_usd, {_cost}) END"


_ESTIMABLE = (
    "name = 'agent_turn' AND ("
    f"{_input} IS NOT NULL OR {_output} IS NOT NULL"
    f" OR {_cache_read} IS NOT NULL OR {_cache_write} IS NOT NULL)"
)


@reading
def turn_charges(run: str) -> dict[str, float]:
    rows = (
        read_connection()
        .execute(
            f"{_charges('run_id = ?')}SELECT span_id, charge_usd FROM charges", (run,)
        )
        .fetchall()
    )
    return {row["span_id"]: row["charge_usd"] for row in rows}


@reading
def unpriced_models(run: str = "") -> dict[str, int]:
    """Models with turns the rate card cannot price, and how many turns each has."""
    clauses = [_ESTIMABLE]
    params: list[Any] = []
    if run:
        clauses.append("run_id = ?")
        params.append(run)
    conn = read_connection()
    rows = conn.execute(
        "SELECT COALESCE(priced_model, json_extract(attrs_json, '$.model')) AS model,"  # noqa: S608
        f" COUNT(*) AS turns FROM spans WHERE {' AND '.join(clauses)} GROUP BY model",
        params,
    ).fetchall()
    found = Counter[str]()
    for row in rows:
        model = str(row["model"] or "")
        if prices.price_for(model) is None:
            found[model or "(no model recorded)"] += row["turns"]
    return dict(found.most_common())


def reprice(run: str = "", missing_only: bool = True) -> dict[str, Any]:
    """Recompute `est_cost_usd` over turns already in the store."""
    clauses = [_ESTIMABLE]
    params: list[Any] = []
    if run:
        clauses.append("run_id = ?")
        params.append(run)
    if missing_only:
        clauses.append("est_cost_usd IS NULL")
    rows = _estimable_turns(clauses, params)
    updates: list[tuple[float, str, str]] = []
    unpriced: Counter[str] = Counter()
    for row in rows:
        model = str(row["priced_model"] or row["model"] or "")
        estimated = _estimated(model, dict(row))
        if estimated is None:
            unpriced[model or "(no model recorded)"] += 1
            continue
        updates.append((estimated, model, row["span_id"]))
    apply_estimates(updates)
    return {
        "considered": len(rows),
        "priced": len(updates),
        "est_cost_usd": sum(value for value, _model, _span in updates),
        "unpriced": dict(unpriced.most_common()),
    }


@reading
def _estimable_turns(clauses: list[str], params: list[Any]) -> list[sqlite3.Row]:
    """Turns matching `clauses`, with everything pricing one needs already coalesced."""
    return (
        read_connection()
        .execute(
            "SELECT span_id, priced_model,"  # noqa: S608
            " json_extract(attrs_json, '$.model') AS model,"
            " json_extract(attrs_json, '$.backend') AS backend,"
            " json_extract(attrs_json, '$.\"session.id\"') AS session_id,"
            f" {_input} AS input_tokens, {_output} AS output_tokens,"
            f" {_cache_read} AS cache_read_tokens, {_cache_write} AS cache_creation_tokens"
            f" FROM spans WHERE {' AND '.join(clauses)}",
            params,
        )
        .fetchall()
    )


@reading
def unpriceable_turns(run: str = "") -> list[dict[str, Any]]:
    """Turns with tokens, no estimate, and a model no rate covers."""
    clauses = [_ESTIMABLE, "est_cost_usd IS NULL"]
    params: list[Any] = []
    if run:
        clauses.append("run_id = ?")
        params.append(run)
    return [
        dict(row)
        for row in _estimable_turns(clauses, params)
        if prices.price_for(str(row["model"] or "")) is None
    ]


@resilient
def apply_estimates(updates: list[tuple[float, str, str]]) -> int:
    """Write `(est_cost_usd, priced_model, span_id)` triples; rows touched."""
    with STORE.writing() as conn:
        conn.executemany(
            "UPDATE spans SET est_cost_usd = ?, priced_model = ? WHERE span_id = ?",
            updates,
        )
    return len(updates)


@reading
def node_costs(run: str = "", limit: int = 100) -> list[dict[str, Any]]:
    """Per-node agent spend for a run: where the money and the rework went."""
    clauses, params = ["name = 'agent_turn'"], []
    if run:
        clauses.append("run_id = ?")
        params.append(run)
    scope = clauses[1] if run else "1=1"
    conn = read_connection()
    rows = conn.execute(
        f"{_charges(scope)}SELECT node,"  # noqa: S608 — clauses are literals; every value is bound
        " COUNT(*) AS turns,"
        " COUNT(DISTINCT json_extract(attrs_json, '$.work_id')) AS work_items,"
        f" SUM({_cost} IS NOT NULL) AS cost_turns,"
        f" SUM({_cost} = 0 AND COALESCE({_output}, 0) > 0) AS zero_cost_turns,"
        " GROUP_CONCAT(DISTINCT json_extract(attrs_json, '$.backend')) AS backends,"
        f" SUM({_charge}) AS cost_usd,"
        " SUM(est_cost_usd) AS est_cost_usd,"
        " SUM(est_cost_usd IS NOT NULL) AS est_turns,"
        f" SUM({_duration}) / 60000.0 AS minutes,"
        f" SUM({_output}) AS output_tokens"
        f" FROM spans LEFT JOIN charges USING (span_id) WHERE {' AND '.join(clauses)}"
        " GROUP BY node ORDER BY cost_usd DESC NULLS LAST, minutes DESC LIMIT ?",
        (*params, *params, max(1, min(int(limit), 1000))),
    ).fetchall()
    total = sum(row["cost_usd"] or 0.0 for row in rows)
    return [
        {
            **dict(row),
            "share": (row["cost_usd"] or 0.0) / total if total else 0.0,
            "turns_per_work_id": (
                row["turns"] / row["work_items"] if row["work_items"] else None
            ),
        }
        for row in rows
    ]
