from __future__ import annotations

import json
import time

import pytest
from test_history import seed
from test_history_dynamic import _row
from test_run_clock import _DB

from groom import history, medians, overview


def _put(run: str, per_item: float | None = 5.0, **fields: object) -> None:
    cost = None if per_item is None else per_item * 2
    history._write(_row(run, 2, cost_usd=cost, **fields))


def _pool(*costs: float, **fields: object) -> None:
    for index, cost in enumerate(costs):
        _put(f"other-{index}", cost, **fields)


def _compared(run: str) -> dict:
    return next(item for item in history.listing(set())["runs"] if item["run_id"] == run)


def _node(name: str, time_s: float, kind: str = "agent") -> dict:
    return {"node": name, "visits": 1, "time_s": time_s, "samples": 1, "longest_s": time_s, "turns": 1, "cost_turns": 1, "cost_usd": 1.0, "output_tokens": 1, "retries": 0, "kind": kind}


def test_the_table_cell_shows_cost_per_item_and_the_signed_percent_from_the_median_of_successful_runs() -> None:
    with _DB():
        _pool(2.0, 4.0, 5.0, 6.0, 8.0)
        _put("judged", 6.0)
        found = _compared("judged")
    assert found["per_item_usd"] == 6.0
    assert found["vs_median_usd"] == 5.0
    assert found["vs_pct"] == pytest.approx(20.0)
    assert found["vs_runs"] == 5


def test_the_median_leaves_out_the_run_it_is_compared_with() -> None:
    with _DB():
        _pool(2.0, 2.0, 2.0, 2.0, 2.0)
        _put("judged", 100.0)
        found = _compared("judged")
        costs = medians.per_item_costs(set())["coder"]
    assert found["vs_median_usd"] == 2.0
    assert found["vs_runs"] == 5
    assert len(costs) == 6
    assert medians.median_of_others(costs, "judged") == (2.0, 5)


def test_under_five_comparable_runs_the_cell_shows_the_cost_per_item_with_no_difference() -> None:
    with _DB():
        _pool(2.0, 4.0, 5.0, 6.0)
        _put("judged", 6.0)
        found = _compared("judged")
    assert found["per_item_usd"] == 6.0
    assert found["vs_pct"] is None
    assert found["vs_median_usd"] is None
    assert found["vs_runs"] == 4


def test_a_run_that_did_not_end_in_success_shows_its_cost_per_item_and_no_comparison() -> None:
    with _DB():
        _pool(2.0, 2.0, 2.0, 2.0, 2.0)
        _put("judged", 9.0, ending="failed")
        found = _compared("judged")
    assert found["per_item_usd"] == 9.0
    assert (found["vs_pct"], found["vs_runs"]) == (None, None)


def test_a_run_with_no_finished_item_shows_no_cost_per_item() -> None:
    with _DB():
        _pool(2.0, 2.0, 2.0, 2.0, 2.0)
        _put("none-done", 9.0, items_done=0)
        _put("no-items", 9.0, items_done=None, items_total=None)
        none_done, no_items = _compared("none-done"), _compared("no-items")
        costs = medians.per_item_costs(set())["coder"]
    for found in (none_done, no_items):
        assert (found["per_item_usd"], found["per_item_est_usd"], found["vs_pct"]) == (None, None, None)
    assert set(costs) == {f"other-{index}" for index in range(5)}


def test_an_estimate_run_stays_out_of_the_median_and_shows_no_comparison() -> None:
    with _DB():
        _pool(2.0, 2.0, 2.0, 2.0, 2.0)
        history._write(_row("estimated", 2, cost_usd=None, est_usd=31.2, priced_turns=0, items_done=2))
        history._write(_row("unpriced", 2, cost_usd=31.2, est_usd=31.2, priced_turns=0, items_done=2))
        _put("judged", 4.0)
        estimated, judged = _compared("estimated"), _compared("judged")
        costs = medians.per_item_costs(set())["coder"]
    assert estimated["per_item_usd"] is None
    assert estimated["per_item_est_usd"] == pytest.approx(15.6)
    assert (estimated["vs_pct"], estimated["vs_runs"]) == (None, None)
    assert not {"estimated", "unpriced"} & set(costs)
    assert judged["vs_runs"] == 5


def test_a_partly_priced_run_stays_in_the_median() -> None:
    with _DB():
        _pool(2.0, 2.0, 2.0, 2.0)
        _put("partial", 2.0, priced_turns=1, turns=4)
        _put("judged", 4.0)
        found = _compared("judged")
    assert found["vs_runs"] == 5
    assert found["vs_pct"] == pytest.approx(100.0)


def test_the_median_covers_every_successful_run_whatever_the_range_and_the_filters() -> None:
    now = time.time()
    with _DB():
        for index in range(3):
            history._write(_row(f"old-{index}", 45 * 24, cost_usd=4.0))
            history._write(_row(f"elsewhere-{index}", 3, cost_usd=4.0, repo="globex", branch="dev"))
        _put("judged", 2.0)
        listing = history.listing(set(), now)
        found = next(item for item in listing["runs"] if item["run_id"] == "judged")
    assert "old-0" not in [item["run_id"] for item in listing["runs"]]
    assert found["vs_runs"] == 6
    assert found["vs_median_usd"] == 2.0
    assert listing["medians"]["coder"]["runs"] == 7


def test_the_totals_median_is_per_workflow_over_every_successful_run_and_counts_them() -> None:
    with _DB():
        _pool(1.0, 2.0, 3.0, 4.0, 5.0)
        _put("book", 8.0, workflow="okf-book")
        _put("failed", 50.0, ending="failed")
        found = history.listing(set())["medians"]
    assert found["coder"] == {"usd": 3.0, "runs": 5}
    assert found["okf-book"] == {"usd": 8.0, "runs": 1}


def test_a_run_that_continued_after_its_summary_stays_out_of_the_median() -> None:
    with _DB():
        _pool(2.0, 2.0, 2.0, 2.0, 2.0)
        _put("resumed", 90.0, ended_ts=None)
        assert medians.per_workflow(medians.per_item_costs(set()))["coder"] == {"usd": 2.0, "runs": 5}


def test_a_run_still_alive_stays_out_of_the_median() -> None:
    with _DB():
        _pool(2.0, 2.0, 2.0, 2.0, 2.0)
        _put("alive", 90.0)
        listing = history.listing({"alive"})
    assert listing["medians"]["coder"] == {"usd": 2.0, "runs": 5}


def test_the_list_with_every_comparison_opens_in_under_two_seconds_and_reads_summaries_only() -> None:
    now = time.time()
    with _DB():
        for index in range(3000):
            history._write(_row(f"bulk-{index}", index / 6, cost_usd=1.0 + index % 7))
        began = time.perf_counter()
        result = history.listing(set(), now)
        took = time.perf_counter() - began
    assert all(item["vs_pct"] is not None for item in result["runs"])
    assert took < 2.0


def test_an_ended_runs_overview_carries_its_comparison_and_a_run_that_has_not_ended_carries_none() -> None:
    now = time.time()
    with _DB():
        _pool(2.0, 2.0, 2.0, 2.0, 2.0)
        seed("judged", now - 3600)
        seed("running", now - 3600, terminal=None)
        history._write(_row("judged", 1, cost_usd=8.0))
        ended, live = overview.run_overview("judged")["compare"], overview.run_overview("running")["compare"]
    assert ended is not None
    assert ended["vs_pct"] == pytest.approx(100.0)
    assert (ended["vs_runs"], ended["ending"], ended["workflow"]) == (5, "success", "coder")
    assert live is None


def test_by_node_reads_each_agent_nodes_mean_against_the_median_of_the_other_successful_runs() -> None:
    nodes = [_node("build", 100.0), _node("review", 10.0), _node("qa", 5.0, "step")]
    with _DB():
        for index in range(5):
            _put(f"other-{index}", 2.0, nodes_json=json.dumps([_node("build", 60.0 + index), _node("review", 10.0)]))
        _put("failed", 2.0, ending="failed", nodes_json=json.dumps([_node("build", 5000.0)]))
        _put("short", 2.0, nodes_json=json.dumps([_node("fresh", 9.0)]))
        found = medians.node_readings("coder", "judged", nodes + [_node("fresh", 9.0)], True)
        refused = medians.node_readings("coder", "judged", nodes, False)
    assert found["build"] == {"median_s": 62.0, "runs": 5}
    assert found["review"] == {"median_s": 10.0, "runs": 5}
    assert found["qa"] is None
    assert found["fresh"] == {"median_s": None, "runs": 1}
    assert refused == {"build": None, "review": None, "qa": None}


def test_a_failed_runs_overview_compares_no_node_and_names_no_median_size() -> None:
    now = time.time()
    with _DB():
        for index in range(5):
            _put(f"other-{index}", 2.0, nodes_json=json.dumps([_node("dev", 60.0)]))
        seed("judged", now - 3600, "fail")
        history._write(_row("judged", 1, ending="failed"))
        found = overview.run_overview("judged")
    assert all(row["norm"] is None for row in found["nodes"])
    assert found["norm_runs"] == 0
    assert found["compare"]["vs_pct"] is None
