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


def _placed(span_id: str, name: str, flow: str | None, state: str | None, *, parent: str, depth: int, turn: bool = False, **kwargs) -> dict:
    attrs: dict = {"workhorse.depth": depth}
    if flow is not None:
        attrs["workhorse.flow"] = flow
    if state is not None:
        attrs["workhorse.state"] = state
    if turn:
        return _span(span_id, "agent_turn", parent=parent, node=name, attrs=attrs, **kwargs)
    return _span(span_id, name, parent=parent, attrs=attrs, **kwargs)


def test_work_in_an_open_flow_is_named_from_its_own_attributes() -> None:
    spans = [
        _placed("n1", "check", "qa", "review", parent="open-state", depth=2),
        _placed("t1", "check", "qa", "review", parent="n1", depth=2, turn=True, duration_ms=4000),
    ]
    rows = build_flows(spans)
    assert [(row["kind"], row["name"]) for row in rows] == [("flow", "qa")]
    assert rows[0]["visits"] is None
    state = rows[0]["children"][0]
    assert (state["kind"], state["name"]) == ("state", "review › check")
    assert UNFINISHED not in [row["name"] for row in rows]


def test_an_open_state_under_an_ended_flow_joins_the_flows_row() -> None:
    spans = [
        _span("f1", "qa", attrs={"workhorse.depth": 0}),
        _state("s1", "plan", parent="f1", depth=1),
        _span("n1", "draft", parent="s1"),
        _placed("n2", "check", "qa", "review", parent="open-state", depth=2),
    ]
    rows = build_flows(spans)
    assert [(row["kind"], row["name"]) for row in rows] == [("flow", "qa")]
    assert rows[0]["visits"] == 1
    assert {child["name"] for child in rows[0]["children"]} == {"plan › draft", "review › check"}


def test_an_ended_state_under_an_open_flow_takes_the_flow_from_the_work() -> None:
    spans = [
        _state("s1", "review", parent="open-flow", depth=1),
        _placed("n1", "check", "qa", "review", parent="s1", depth=2),
    ]
    rows = build_flows(spans)
    assert [(row["kind"], row["name"]) for row in rows] == [("flow", "qa")]
    assert rows[0]["visits"] is None
    assert rows[0]["children"][0]["name"] == "review › check"


def test_an_open_state_at_depth_zero_sits_under_the_workflow_row() -> None:
    spans = [
        _placed("n1", "pick", "", "resolve", parent="open-state", depth=1),
        _placed("n2", "land", "", "resolve", parent="open-state", depth=1),
    ]
    rows = build_flows(spans)
    assert [(row["kind"], row["name"]) for row in rows] == [("workflow", "coder")]
    state = rows[0]["children"][0]
    assert (state["kind"], state["name"]) == ("state", "resolve")
    assert state["visits"] is None


def test_work_with_no_flow_or_state_attributes_keeps_the_unfinished_row() -> None:
    spans = [_span("n1", "alpha", parent="gone", attrs={"workhorse.depth": 2})]
    rows = build_flows(spans)
    assert [row["name"] for row in rows] == [UNFINISHED]
    assert rows[0]["title"] == "gone"


def test_a_flow_that_ends_between_two_reads_stays_one_row() -> None:
    open_work = [_placed("n1", "check", "qa", "review", parent="open-state", depth=2)]
    ended = [
        *open_work,
        _span("f1", "qa", attrs={"workhorse.depth": 0}),
        _state("s1", "review", parent="f1", depth=1),
        _placed("n2", "check", "qa", "review", parent="s1", depth=2),
    ]
    before = build_flows(open_work)
    after = build_flows(ended)
    assert [row["name"] for row in before] == [row["name"] for row in after] == ["qa"]
    assert before[0]["visits"] is None
    assert after[0]["visits"] == 1
    assert after[0]["children"][0]["name"] == "review › check"
    assert after[0]["children"][0]["visits"] == 2


def test_a_row_for_an_open_flow_has_no_visit_count_and_no_zero() -> None:
    rows = build_flows([_placed("n1", "check", "qa", "", parent="open-flow", depth=1)])
    assert rows[0]["visits"] is None


def _engine_spans() -> list[dict]:
    import tempfile as tmpfile
    from typing import Any

    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from pydantic import BaseModel

    from workhorse import otel
    from workhorse.artifacts import ArtifactWriter
    from workhorse.config_run import RunConfig
    from workhorse.pyflow import Blueprint, Continue, Done, Workflow
    from workhorse.pyflow.driver import drive
    from workhorse.pyflow.engine import RunEnv

    class Meter:
        def create_gauge(self, *_a, **_k):
            return None

        def create_counter(self, *_a, **_k):
            return None

    class Out(BaseModel):
        ok: bool = True

    blueprint = Blueprint("coder")

    @blueprint.node
    def pick(logger: Any) -> Out:
        otel.turn_start("pick", None, None, 1.0)
        otel.turn_end()
        return Out()

    @blueprint.node
    def check(logger: Any) -> Out:
        otel.turn_start("check", None, None, 1.0)
        otel.turn_end()
        return Out()

    @blueprint.node
    def loose(logger: Any) -> Out:
        return Out()

    class Review(Workflow):
        def start(self) -> Any:
            self.call(check)
            return Continue(None, self.report)

        def report(self) -> Any:
            self.call(loose)
            return Done(None)

    class Parent(Workflow):
        def start(self) -> Any:
            self.call(pick)
            return Continue(None, self.review)

        def review(self) -> Any:
            return Done(self.handoff(Review))

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    def build(workflow, run_id, run_dir, settings):
        telemetry = otel._Telemetry(trace, provider.get_tracer("t"), Meter(), lambda: None, 30.0)
        telemetry.start_root(workflow)
        return telemetry

    previous = otel.install(otel.TelemetryHost(settings=otel.OtelSettings(forced=True), build=build))
    try:
        with tmpfile.TemporaryDirectory() as tmp:
            writer = ArtifactWriter("coder", Path(tmp) / "runs", run_id="t")
            env = RunEnv(
                writer=writer,
                workflow_dir=Path(tmp),
                session_id_path=writer.run_dir / ".session_id",
                config=RunConfig(),
            )
            otel.start_run("coder", "t")
            drive(Parent(), env)
            otel.end_run("done")
    finally:
        otel.install(previous)
    spans = []
    for number, span in enumerate(exporter.get_finished_spans()):
        context = span.get_span_context()
        attrs = dict(span.attributes or {})
        assert context is not None
        spans.append(
            {
                "span_id": format(context.span_id, "016x"),
                "trace_id": format(context.trace_id, "032x"),
                "parent_id": format(span.parent.span_id, "016x") if span.parent else "",
                "workflow": "coder",
                "node": str(attrs.get("workhorse.node", "")),
                "name": span.name,
                "start_ts": float(number),
                "end_ts": float(number) + 1.0,
                "attrs": attrs,
                "profile_duration_ms": 1000.0 if span.name == "agent_turn" else None,
                "profile_cost_usd": 1.0 if span.name == "agent_turn" else None,
                "profile_output_tokens": None,
            }
        )
    return spans


def _shape(rows: list[dict]) -> list[tuple]:
    return [
        (row["kind"], row["name"], row["time_s"], row["turns"], row["cost_usd"], _shape(row["children"]))
        for row in rows
    ]


def test_dropping_the_flow_and_state_spans_of_a_finished_run_changes_no_row() -> None:
    spans = _engine_spans()
    containers = {span["parent_id"] for span in spans if span["parent_id"]}
    kept = [
        span
        for span in spans
        if span["attrs"].get("workhorse.span_kind") != "state"
        and not (span["name"] != "agent_turn" and span["span_id"] in containers)
        and not span["name"].startswith("run:")
    ]
    assert len(kept) < len(spans)
    assert any(span["attrs"].get("workhorse.span_kind") == "state" for span in spans)
    whole = build_flows([span for span in spans if not span["name"].startswith("run:")])
    assert _shape(build_flows(kept)) == _shape(whole)
    assert len(whole) >= 2
    assert any(row["kind"] == "flow" for row in whole)


def test_an_empty_flow_name_survives_the_wire_and_the_store() -> None:
    from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from groom import otlp

    exporter = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource({"run_id": "run-1"}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    provider.get_tracer("t").start_span(
        "pick", attributes={"workhorse.flow": "", "workhorse.state": "resolve"}
    ).end()
    parsed = otlp.parse_traces(encode_spans(exporter.get_finished_spans()).SerializeToString())
    with _DB():
        store.insert_spans(parsed)
        stored = store._run_spans("run-1")
    assert stored[0]["attrs"]["workhorse.flow"] == ""
    assert stored[0]["attrs"]["workhorse.state"] == "resolve"


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


def test_a_state_is_a_step_when_nothing_but_infra_sits_under_it() -> None:
    from groom.flows import state_steps

    infra = {"workhorse.span_kind": "infra"}
    spans = [
        _state("bare", "bring_up"),
        _state("infra-only", "route"),
        _span("i1", "infra:compose", parent="infra-only", attrs=infra),
        _state("with-node", "work"),
        _span("n1", "lint", parent="with-node"),
        _state("outer", "wrap"),
        _state("inner", "inner", parent="outer"),
        _state("with-turn", "agent"),
        _turn("t1", "with-turn", "qa-story"),
        _state("with-wait", "gate"),
        _span("w1", "wait:operator", parent="with-wait", attrs={"workhorse.span_kind": "wait"}),
    ]
    assert [one["span_id"] for one in state_steps(spans)] == ["bare", "infra-only", "inner"]


def _flow_with_steps() -> list[dict]:
    return [
        _span("f1", "qa", attrs={"workhorse.depth": 0}, seconds=100),
        _state("s1", "bring_up", parent="f1", depth=1),
        _span("i1", "infra:compose", parent="s1", attrs={"workhorse.span_kind": "infra"}, seconds=4),
        _state("s2", "review", parent="f1", depth=1),
        _span("n1", "check", parent="s2", seconds=30),
        _turn("t1", "n1", "check", duration_ms=25000, cost=1.5),
    ]


def test_a_state_step_adds_its_time_to_its_flow_and_node_rows_with_no_cost() -> None:
    from groom.flows import node_breakdown

    rows = build_flows(_flow_with_steps())
    assert rows[0]["time_s"] == 35
    assert rows[0]["cost_usd"] == 1.5
    nodes = {row["node"]: row for row in node_breakdown(rows)}
    assert nodes["bring_up"]["time_s"] == 10
    assert nodes["bring_up"]["cost_usd"] is None
    assert nodes["bring_up"]["visits"] == 1
    assert nodes["check"]["time_s"] == 25


def test_a_state_step_inside_a_container_node_is_counted_once() -> None:
    from groom.flows import node_breakdown

    spans = [
        _span("f1", "qa", attrs={"workhorse.depth": 0}, seconds=100),
        _state("s1", "review", parent="f1", depth=1),
        _span("n1", "wrapper", parent="s1", seconds=50),
        _state("s2", "inner", parent="n1", depth=2),
        _span("n2", "leaf", parent="n1", seconds=20),
    ]
    rows = build_flows(spans)
    assert {row["name"]: row["time_s"] for row in rows} == {"qa": 20, "wrapper": 10}
    assert sum(row["time_s"] for row in node_breakdown(rows)) == 30


def test_an_open_state_step_is_counted_once_beside_the_unfinished_rows() -> None:
    spans = [
        _placed("n1", "check", "qa", "review", parent="open-state", depth=2),
        _span("orphan", "alpha", parent="gone", attrs={"workhorse.depth": 2}),
        _state("s9", "bring_up", parent="open-state", depth=2),
    ]
    rows = build_flows(spans)
    assert sum(row["time_s"] for row in rows) == 30
