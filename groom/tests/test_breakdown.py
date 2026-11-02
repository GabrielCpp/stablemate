"""The By node and By work item breakdowns: their data, and the numbers they must share with the flow tree."""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from groom import flows, norms, overview, pools, store
from groom import app as groom_app
from groom.models import WorkflowContainer

RUN = "live"


class _DB:
    def __enter__(self) -> _DB:
        self._tmp = tempfile.TemporaryDirectory()
        self._previous = os.environ.get("GROOM_DB")
        os.environ["GROOM_DB"] = str(Path(self._tmp.name) / "groom.db")
        store.reset()
        norms.reset()
        return self

    def __exit__(self, *exc: object) -> None:
        store.reset()
        norms.reset()
        if self._previous is None:
            os.environ.pop("GROOM_DB", None)
        else:
            os.environ["GROOM_DB"] = self._previous
        self._tmp.cleanup()


def _span(span_id: str, run: str, parent: str, node: str, name: str, at: float, seconds: float, attrs: dict | None = None) -> dict:
    return {
        "span_id": span_id, "trace_id": run, "parent_id": parent, "run_id": run, "workflow": "coder",
        "repo": "acme", "branch": "main", "node": node, "name": name, "run_dir": "",
        "start_ts": at, "end_ts": at + seconds, "status": "OK", "attrs": attrs or {},
    }


def _turn(span_id: str, run: str, parent: str, node: str, at: float, seconds: float, cost: float, item: str | None = None, done: int | None = None) -> dict:
    attrs: dict = {"backend": "claude", "duration_ms": seconds * 1000, "total_cost_usd": cost}
    if item is not None:
        attrs["work_id"] = item
    if done is not None:
        attrs["progress"] = f"{done}/3"
    return _span(span_id, run, parent, node, "agent_turn", at, seconds, attrs)


def _history(ok: int, failed: int) -> None:
    spans = []
    for kind, count, terminal, seconds in (("ok", ok, "terminal", 60.0), ("bad", failed, "fail", 600.0)):
        for index in range(count):
            run = f"{kind}{index}"
            spans.append(_span(f"{run}-root", run, "", "run:coder", "run:coder", 1000.0, 900.0, {"workhorse.terminal": terminal}))
            spans.append(_turn(f"{run}-t", run, "", "build", 1000.0, seconds, 1.0))
    store.insert_spans(spans)


def _live(items: tuple[str, ...] = ("a", "b", "c")) -> None:
    spans = [_span("state", RUN, "", "work", "work", 5000.0, 900.0, {"workhorse.span_kind": "state", "workhorse.depth": 0})]
    at = 5000.0
    for position, item in enumerate(items):
        laps = 2 if position == 0 else 1
        for lap in range(laps):
            tag = item if item else None
            node = f"{position}-{lap}"
            spans.append(_span(f"n{node}", RUN, "state", "build", "build", at, 90.0, {"workhorse.depth": 1}))
            spans.append(_turn(f"t{node}", RUN, f"n{node}", "build", at, 90.0, 2.0, tag, position))
            at += 100.0
    spans.append(_span("lint", RUN, "state", "lint", "lint", at, 30.0, {"workhorse.depth": 1}))
    spans.append(_span("loose", RUN, "state", "build", "build", at + 40, 10.0, {"workhorse.depth": 1}))
    spans.append(_turn("loose-t", RUN, "loose", "build", at + 40, 10.0, 0.5))
    spans.append(_span("progress", RUN, "state", "report", "report", at + 60, 5.0, {"workhorse.depth": 1, "progress": f"{len(items) - 1}/3"}))
    store.insert_spans(spans)


def test_the_median_beside_a_node_counts_successful_runs_only():
    with _DB():
        _history(ok=5, failed=6)
        _live()
        data = overview.run_overview(RUN)
        build = next(row for row in data["nodes"] if row["node"] == "build")
        assert build["norm"] == {"median_s": 60.0, "runs": 5}
        assert data["norm_runs"] == 5


def test_fewer_than_five_successful_runs_leave_the_comparison_blank_and_the_count_visible():
    with _DB():
        _history(ok=4, failed=6)
        _live()
        data = overview.run_overview(RUN)
        build = next(row for row in data["nodes"] if row["node"] == "build")
        assert build["norm"] == {"median_s": None, "runs": 4}
        assert data["norm_runs"] == 4


def test_the_table_and_the_strip_read_one_median_from_one_cache():
    with _DB():
        _history(ok=5, failed=0)
        _live()
        data = overview.run_overview(RUN)
        build = next(row for row in data["nodes"] if row["node"] == "build")
        cached = norms.cached("coder", "build")
        assert cached is not None
        assert norms.reading(cached["turn"]) == build["norm"]
        before = dict(norms.CACHE)
        overview.run_overview(RUN)
        assert norms.CACHE == before


def test_the_sample_size_comes_from_the_cache_without_another_scan_per_update(monkeypatch):
    with _DB():
        _history(ok=5, failed=0)
        _live()
        overview.run_overview(RUN)
        reads = []
        monkeypatch.setattr(store, "node_norms", lambda *args: reads.append(args) or {})
        overview.run_overview(RUN)
        assert reads == []


def test_a_norm_that_changes_after_its_first_read_moves_the_pane_revision_and_the_first_read_does_not():
    with _DB():
        _history(ok=5, failed=0)
        _live()
        wf = WorkflowContainer(container_id="c1", name="c1", run_id=RUN)
        overview.run_overview(RUN)
        start = groom_app._figures_rev(wf)
        assert norms.revision() == 0
        store.insert_spans(
            [_span("late-root", "late", "", "run:coder", "run:coder", 1000.0, 900.0, {"workhorse.terminal": "terminal"}),
             _turn("late-t", "late", "", "build", 1000.0, 400.0, 1.0)]
        )
        try:
            assert asyncio.run(norms.refresh("coder", "build")) is True
            assert groom_app._figures_rev(wf) == start + 1
            assert asyncio.run(norms.refresh("coder", "build")) is False
            assert groom_app._figures_rev(wf) == start + 1
        finally:
            pools.shutdown_all()


def test_the_node_rows_add_up_to_the_flow_trees_total_and_merge_a_node_reached_twice():
    with _DB():
        _live()
        data = overview.run_overview(RUN)
        assert sum(row["time_s"] for row in data["nodes"]) == pytest.approx(data["time_s"])
        costs = [row["cost_usd"] for row in data["flows"] if row["cost_usd"] is not None]
        assert sum(row["cost_usd"] or 0 for row in data["nodes"]) == pytest.approx(sum(costs))
        build = next(row for row in data["nodes"] if row["node"] == "build")
        assert build["kind"] == "agent"
        assert build["samples"] == build["turns"] == 5
        assert build["longest_s"] == 90.0
        lint = next(row for row in data["nodes"] if row["node"] == "lint")
        assert (lint["kind"], lint["samples"], lint["longest_s"]) == ("step", 1, 30.0)


def test_node_breakdown_merges_a_node_that_sits_in_two_states():
    def leaf(node: str, seconds: float, cost: float | None) -> dict:
        return {
            "kind": "node", "node": node, "name": node, "visits": 1, "time_s": seconds, "turns": 1, "samples": 1,
            "longest_s": seconds, "cost_turns": 1 if cost is not None else 0, "cost_usd": cost, "output_tokens": 0,
            "retries": 0, "children": [],
        }

    tree = [
        {"kind": "flow", "name": "f", "children": [
            {"kind": "state", "name": "one", "children": [leaf("qa", 10.0, 1.0)]},
            {"kind": "state", "name": "two", "children": [leaf("qa", 30.0, None), leaf("dev", 5.0, None)]},
        ]},
    ]
    merged = {row["node"]: row for row in flows.node_breakdown(tree)}
    assert merged["qa"]["time_s"] == 40.0
    assert merged["qa"]["visits"] == 2
    assert merged["qa"]["longest_s"] == 30.0
    assert merged["qa"]["cost_usd"] == 1.0
    assert merged["dev"]["cost_usd"] is None


def test_the_item_rows_read_the_laps_groom_loops_counts():
    with _DB():
        _live()
        data = overview.run_overview(RUN)
        rows = {row["work_id"]: row for row in data["items"]["rows"]}
        loops = {row["node"]: row for row in store.loop_convergence(run=RUN, min_work_items=1)}
        assert loops["build"]["work_items"] == len(rows)
        assert loops["build"]["turns"] == sum(row["nodes"]["build"] for row in rows.values())
        assert rows["a"]["passes"] == 2
        assert rows["b"]["passes"] == 1


def test_items_and_the_outside_row_add_up_to_the_trees_totals():
    with _DB():
        _live()
        data = overview.run_overview(RUN)
        items = data["items"]
        spent = sum(row["seconds"] for row in items["rows"])
        assert spent + items["outside"]["time_s"] == pytest.approx(items["total"]["time_s"])
        assert items["total"]["time_s"] == pytest.approx(data["time_s"])
        paid = sum(row["cost_usd"] or 0 for row in items["rows"])
        assert paid + items["outside"]["cost_usd"] == pytest.approx(items["total"]["cost_usd"])
        assert items["total"]["cost_usd"] == pytest.approx(data["figures"]["cost_usd"])
        assert items["outside"]["cost_usd"] == pytest.approx(0.5)


def test_an_item_is_done_when_the_runs_count_moved_past_it():
    with _DB():
        _live()
        data = overview.run_overview(RUN)
        outcomes = {row["work_id"]: row["outcome"] for row in data["items"]["rows"]}
        assert outcomes == {"a": "done", "b": "done", "c": "uncounted"}
        assert data["figures"]["items_done"] == 2


def test_a_run_with_no_work_item_has_no_item_view():
    with _DB():
        _live(items=("",))
        store.insert_spans([_turn("plain", "plain", "", "build", 9000.0, 20.0, 1.0)])
        assert overview.run_overview("plain")["items"] is None


def test_an_item_with_no_reported_count_has_an_unknown_outcome():
    with _DB():
        spans = [
            _turn("w1", "bare", "", "build", 100.0, 10.0, 1.0, item="x"),
            _turn("w2", "bare", "", "build", 200.0, 10.0, 1.0, item="y"),
        ]
        store.insert_spans(spans)
        rows = overview.run_overview("bare")["items"]["rows"]
        assert [row["outcome"] for row in rows] == ["unknown", "unknown"]
