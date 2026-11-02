"""The flow tree: where finished work lands, and what is never guessed."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from litestar.testing import TestClient

from groom import app as groom_app
from groom import cli, overview, store
from groom.flows import UNFINISHED, build_flows


def _span(
    span_id: str,
    name: str,
    *,
    parent: str = "",
    node: str = "",
    attrs: dict | None = None,
    start: float = 0.0,
    seconds: float = 10.0,
    cost: float | None = None,
    tokens: int | None = None,
    duration_ms: float | None = None,
    trace: str = "t1",
) -> dict:
    return {
        "span_id": span_id,
        "trace_id": trace,
        "parent_id": parent,
        "workflow": "coder",
        "node": node or name,
        "name": name,
        "start_ts": start,
        "end_ts": start + seconds,
        "attrs": attrs or {},
        "profile_duration_ms": duration_ms,
        "profile_cost_usd": cost,
        "profile_output_tokens": tokens,
    }


def _state(span_id: str, name: str, *, parent: str = "", depth: int | None = None) -> dict:
    attrs: dict = {"workhorse.span_kind": "state"}
    if depth is not None:
        attrs["workhorse.depth"] = depth
    return _span(span_id, name, parent=parent, attrs=attrs)


def _turn(span_id: str, parent: str, node: str, **kwargs) -> dict:
    return _span(span_id, "agent_turn", parent=parent, node=node, **kwargs)


def _by_name(rows: list[dict]) -> dict[str, dict]:
    return {row["name"]: row for row in rows}


def test_an_ended_flow_is_named_from_its_own_span() -> None:
    spans = [
        _span("f1", "qa", attrs={"workhorse.depth": 0}),
        _state("s1", "review", parent="f1", depth=1),
        _span("n1", "check", parent="s1"),
        _span("n2", "report", parent="s1"),
        _turn("t1", "n1", "check", duration_ms=4000, cost=1.0),
        _turn("t2", "n2", "report", duration_ms=6000, cost=2.0),
    ]
    rows = build_flows(spans)
    assert [row["name"] for row in rows] == ["qa"]
    flow = rows[0]
    assert flow["kind"] == "flow"
    assert flow["visits"] == 1
    assert flow["cost_usd"] == 3.0
    state = flow["children"][0]
    assert (state["kind"], state["name"]) == ("state", "review")
    assert [child["name"] for child in state["children"]] == ["report", "check"]
    assert state["time_s"] == 10.0


def test_depth_zero_states_sit_under_the_runs_own_workflow() -> None:
    spans = [
        _state("s1", "resolve", depth=0),
        _span("n1", "pick", parent="s1"),
        _span("n2", "land", parent="s1"),
    ]
    rows = build_flows(spans)
    assert [(row["kind"], row["name"]) for row in rows] == [("workflow", "coder")]
    assert rows[0]["visits"] is None
    assert rows[0]["children"][0]["name"] == "resolve"


def test_work_under_an_unexported_parent_gets_one_unfinished_row_per_parent() -> None:
    spans = [
        _span("n1", "alpha", parent="gone-1", attrs={"workhorse.depth": 2}),
        _span("n2", "beta", parent="gone-1", attrs={"workhorse.depth": 2}),
        _span("n3", "gamma", parent="gone-2", attrs={"workhorse.depth": 2}),
    ]
    rows = build_flows(spans)
    assert [row["name"] for row in rows] == [UNFINISHED, UNFINISHED]
    assert {row["title"] for row in rows} == {"gone-1", "gone-2"}
    assert all(row["visits"] is None for row in rows)
    assert UNFINISHED == "Unfinished flow or state"


def test_a_parentless_node_is_not_given_an_invented_flow() -> None:
    rows = build_flows([_span("n1", "alpha", attrs={"workhorse.depth": 0})])
    assert [(row["kind"], row["name"]) for row in rows] == [("workflow", "coder")]
    assert [child["name"] for child in rows[0]["children"]] == ["alpha"]


def test_a_state_with_one_node_collapses_to_one_row() -> None:
    spans = [
        _state("s1", "resolve", depth=0),
        _span("n1", "resolve-operator", parent="s1"),
        _state("s2", "land", depth=0),
        _span("n2", "land", parent="s2"),
    ]
    names = {row["name"] for row in build_flows(spans)[0]["children"]}
    assert names == {"resolve › resolve-operator", "land"}


def test_retries_count_turns_beyond_one_per_visit() -> None:
    spans = [
        _state("s1", "work", depth=0),
        _span("n1", "qa", parent="s1"),
        _turn("t1", "n1", "qa", duration_ms=1000),
        _turn("t2", "n1", "qa", duration_ms=1000),
        _turn("t3", "n1", "qa", duration_ms=1000),
    ]
    node = _by_name(build_flows(spans)[0]["children"])["work › qa"]
    assert node["turns"] == 3
    assert node["retries"] == 2
    assert node["visits"] == 1


def test_node_time_is_the_turn_time_when_turns_exist() -> None:
    spans = [
        _state("s1", "work", depth=0),
        _span("n1", "qa", parent="s1", seconds=500.0),
        _turn("t1", "n1", "qa", duration_ms=2000),
    ]
    assert build_flows(spans)[0]["time_s"] == 2.0


def test_without_cost_the_row_carries_output_tokens_and_no_figure() -> None:
    spans = [
        _state("s1", "work", depth=0),
        _span("n1", "qa", parent="s1"),
        _turn("t1", "n1", "qa", duration_ms=1000, tokens=700),
        _turn("t2", "n1", "qa", duration_ms=1000, tokens=300),
    ]
    row = build_flows(spans)[0]
    assert row["cost_usd"] is None
    assert row["cost_turns"] == 0
    assert row["output_tokens"] == 1000


def test_rows_sort_by_time_descending() -> None:
    spans = [
        _state("s1", "quick", depth=0),
        _span("n1", "a", parent="s1", seconds=1.0),
        _state("s2", "slow", depth=0),
        _span("n2", "b", parent="s2", seconds=9.0),
    ]
    assert [row["name"] for row in build_flows(spans)[0]["children"]] == ["slow › b", "quick › a"]


class _DB:
    def __enter__(self) -> _DB:
        self._tmp = tempfile.TemporaryDirectory()
        self._previous = os.environ.get("GROOM_DB")
        os.environ["GROOM_DB"] = str(Path(self._tmp.name) / "groom.db")
        store.reset()
        return self

    def __exit__(self, *exc: object) -> None:
        store.reset()
        if self._previous is None:
            os.environ.pop("GROOM_DB", None)
        else:
            os.environ["GROOM_DB"] = self._previous
        self._tmp.cleanup()


def _stored(span_id: str, parent: str, node: str, name: str, attrs: dict, at: float) -> dict:
    return {
        "span_id": span_id, "trace_id": "t", "parent_id": parent, "run_id": "run-1",
        "workflow": "coder", "repo": "acme", "branch": "main", "node": node, "name": name,
        "run_dir": "", "start_ts": at, "end_ts": at + 60, "status": "OK", "attrs": attrs,
    }


def _seed_run() -> None:
    turn = {"backend": "claude", "duration_ms": 60000, "usage.output_tokens": 100}
    store.insert_spans(
        [
            _stored("s0", "", "work", "work", {"workhorse.span_kind": "state", "workhorse.depth": 0}, 100),
            _stored("n1", "s0", "qa", "qa", {"workhorse.depth": 1}, 110),
            _stored("t1", "n1", "qa", "agent_turn", {**turn, "total_cost_usd": 1.5}, 120),
            _stored("t2", "n1", "qa", "agent_turn", {**turn, "total_cost_usd": 0.5}, 190),
            _stored("n2", "gone", "dev", "dev", {"workhorse.depth": 2}, 300),
            _stored("t3", "n2", "dev", "agent_turn", dict(turn), 310),
        ]
    )


def test_overview_prices_turns_and_reports_the_last_finished_turn() -> None:
    with _DB():
        _seed_run()
        result = overview.run_overview("run-1")
    assert result["finished"] is True
    assert result["cost"]["turns"] == 3
    assert result["cost"]["priced_turns"] == 2
    assert result["cost"]["usd"] == 2.0
    assert result["cost"]["reports_cost"] is True
    assert result["as_of_ts"] == 370
    names = [row["name"] for row in result["flows"]]
    assert UNFINISHED in names


def test_overview_without_spans_is_not_finished() -> None:
    with _DB():
        result = overview.run_overview("nothing")
    assert result["finished"] is False
    assert result["cost"]["usd"] is None
    assert result["cost"]["reports_cost"] is False
    assert result["flows"] == []


def test_overview_of_a_backend_with_no_cost_reports_none() -> None:
    with _DB():
        store.insert_spans(
            [
                _stored("s0", "", "work", "work", {"workhorse.span_kind": "state", "workhorse.depth": 0}, 100),
                _stored("n1", "s0", "qa", "qa", {}, 110),
                _stored("t1", "n1", "qa", "agent_turn", {"backend": "codex", "duration_ms": 1000, "usage.output_tokens": 50}, 120),
            ]
        )
        result = overview.run_overview("run-1")
    assert result["cost"]["usd"] is None
    assert result["cost"]["reports_cost"] is False
    assert result["cost"]["output_tokens"] == 50


def test_the_overview_endpoint_serves_the_same_figures() -> None:
    with _DB():
        _seed_run()
        with TestClient(app=groom_app.create_app()) as client:
            response = client.get("/api/run/run-1/overview")
    assert response.status_code == 200
    body = response.json()
    assert body["cost"]["usd"] == 2.0
    assert body["finished"] is True


def test_the_profile_carries_the_flow_tree_and_the_cli_prints_it() -> None:
    with _DB():
        _seed_run()
        result = store.run_profile("run-1")
    assert result is not None
    assert any(row["name"] == UNFINISHED for row in result["flows"])
    text = cli._format_profile(result)
    assert "flows (flow > state > node)" in text
    assert UNFINISHED in text
