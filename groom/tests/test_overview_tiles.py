from __future__ import annotations

import os
import tempfile
from pathlib import Path

from litestar.testing import TestClient

from groom import alerts, churn, figures, overview, state, store
from groom import app as groom_app


class _DB:
    def __enter__(self) -> _DB:
        self._tmp = tempfile.TemporaryDirectory()
        self._previous = os.environ.get("GROOM_DB")
        os.environ["GROOM_DB"] = str(Path(self._tmp.name) / "groom.db")
        store.reset()
        state.RUNS.clear()
        return self

    def __exit__(self, *exc: object) -> None:
        store.reset()
        state.RUNS.clear()
        if self._previous is None:
            os.environ.pop("GROOM_DB", None)
        else:
            os.environ["GROOM_DB"] = self._previous
        self._tmp.cleanup()


def _span(
    span_id: str,
    parent: str,
    node: str,
    name: str,
    attrs: dict,
    at: float,
    *,
    status: str = "OK",
    seconds: float = 60,
    generation: int | None = None,
    trace: str = "t",
) -> dict:
    return {
        "span_id": span_id, "trace_id": trace, "parent_id": parent, "run_id": "run-1",
        "workflow": "coder", "repo": "acme", "branch": "main", "node": node, "name": name,
        "run_dir": "", "start_ts": at, "end_ts": at + seconds, "status": status, "attrs": attrs,
        "resume_generation": generation,
    }


TURN = {"backend": "claude", "duration_ms": 60000, "usage.output_tokens": 100, "total_cost_usd": 1.0}

STATE = {"workhorse.span_kind": "state", "workhorse.depth": 0}
OPERATOR_WAIT = {"workhorse.span_kind": "wait", "workhorse.wait_kind": "operator", "workhorse.wait_outcome": "completed"}


def _churning(prefix: str, visits: int, at: float, **labels: str) -> list[dict]:
    return [_span(f"{prefix}{index}", "s0", "pick", "pick", {"work_id": "a", **labels}, at + index * 10, seconds=5) for index in range(visits)]


def _standing() -> dict:
    return overview.run_overview("run-1")["standing"]


def test_the_problem_count_adds_failed_steps_retries_failed_gate_checks_and_churn() -> None:
    with _DB():
        store.insert_spans(
            [
                _span("s0", "", "work", "work", STATE, 100),
                _span("bad", "s0", "qa", "qa", {}, 110, status="ERROR"),
                _span("n2", "s0", "dev", "dev", {}, 200),
                _span("t1", "n2", "dev", "agent_turn", dict(TURN), 210),
                _span("t2", "n2", "dev", "agent_turn", dict(TURN), 280),
                _span("g1", "s0", "run_gate", "run_gate", {"workhorse.out.gate": "lint", "workhorse.out.status": "dirty"}, 400),
                _span("g2", "s0", "run_gate", "run_gate", {"workhorse.out.gate": "test", "workhorse.out.status": "clean"}, 470),
                *_churning("c", 5, 600),
            ]
        )
        standing = _standing()
    assert standing["failed_steps"] == 1
    assert standing["retries"] == 1
    assert standing["failed_gate_checks"] == 1
    assert standing["churn_alerts"] == 1
    assert standing["problems"] == 4


def test_an_answered_gate_is_counted_as_a_gate_and_not_as_a_problem() -> None:
    with _DB():
        store.insert_spans(
            [
                _span("s0", "", "work", "work", STATE, 100),
                _span("n1", "s0", "qa", "qa", {}, 110),
                _span("w1", "s0", "await_operator", "await_operator", dict(OPERATOR_WAIT), 200, seconds=420),
                _span("w2", "s0", "await_operator", "await_operator", {**OPERATOR_WAIT, "workhorse.wait_kind": "cap"}, 700),
            ]
        )
        standing = _standing()
    assert standing["gates"] == 1
    assert standing["gate_wait_s"] == 420
    assert standing["problems"] == 0


def test_a_failure_with_a_failing_span_beneath_it_counts_once() -> None:
    with _DB():
        store.insert_spans(
            [
                _span("s0", "", "work", "work", STATE, 100, status="ERROR"),
                _span("outer", "s0", "qa", "qa", {}, 110, status="ERROR"),
                _span("t1", "outer", "qa", "agent_turn", dict(TURN), 120, status="ERROR"),
                _span("root", "", "coder", "run:coder", {}, 90, status="ERROR"),
            ]
        )
        standing = _standing()
    assert standing["failed_steps"] == 1


def test_problems_never_fall_below_the_backend_retries() -> None:
    with _DB():
        store.insert_spans(
            [
                _span("s0", "", "work", "work", STATE, 100),
                _span("n1", "s0", "dev", "dev", {}, 110),
                _span("n2", "s0", "dev", "dev", {}, 400),
                *[_span(f"t{index}", "n1", "dev", "agent_turn", dict(TURN), 120 + index * 70) for index in range(3)],
                *[_span(f"u{index}", "n2", "dev", "agent_turn", dict(TURN), 410 + index * 70) for index in range(2)],
            ]
        )
        standing = _standing()
    assert standing["retries"] == 3
    assert standing["problems"] >= standing["retries"]


def test_the_retries_on_the_tile_equal_the_sum_of_the_trees_retries_column() -> None:
    with _DB():
        store.insert_spans(
            [
                _span("s0", "", "work", "work", STATE, 100),
                _span("n1", "s0", "qa", "qa", {}, 110),
                _span("t1", "n1", "qa", "agent_turn", dict(TURN), 120),
                _span("t2", "n1", "qa", "agent_turn", dict(TURN), 190),
                _span("t3", "n1", "qa", "agent_turn", dict(TURN), 260),
                _span("n2", "gone", "dev", "dev", {}, 300),
                _span("t4", "n2", "dev", "agent_turn", dict(TURN), 310),
                _span("t5", "n2", "dev", "agent_turn", dict(TURN), 380),
            ]
        )
        result = overview.run_overview("run-1")
    column = sum(row["retries"] for row in result["flows"])
    assert column == 3
    assert result["standing"]["retries"] == column


def test_churn_is_derived_from_stored_spans_and_holds_with_no_hot_cache() -> None:
    with _DB():
        store.insert_spans([_span("s0", "", "work", "work", STATE, 100), *_churning("c", 7, 200)])
        assert state.RUNS == {}
        standing = _standing()
    assert standing["churn_alerts"] == 1


def test_work_that_moves_on_is_not_churn() -> None:
    with _DB():
        spans = [
            _span(f"c{index}", "s0", "pick", "pick", {"work_id": f"item-{index}"}, 200 + index * 10, seconds=5)
            for index in range(9)
        ]
        store.insert_spans([_span("s0", "", "work", "work", STATE, 100), *spans])
        standing = _standing()
    assert standing["churn_alerts"] == 0


def _ingest_form(spans: list[dict]) -> list[dict]:
    return [{**span, "attrs": dict(span["attrs"])} for span in spans]


def test_the_derived_churn_count_matches_the_alert_rule_over_the_same_spans() -> None:
    cut = _span("cut", "s0", "pick", "pick", {"work_id": "a", "workhorse.cut": True}, 150, seconds=5)
    spans = [
        cut,
        *_churning("a", 12, 200),
        *_churning("b", 6, 500, phase="second"),
        *[_span(f"d{index}", "s0", "pick", "pick", {"work_id": f"d{index}"}, 700 + index * 10, seconds=5) for index in range(8)],
    ]
    with _DB():
        state.RUNS.clear()
        ordered = sorted(_ingest_form(spans), key=lambda span: span["end_ts"])
        fired = [alert for alert in alerts.ingest_spans(ordered, now=1000.0) if alert.rule == "CHURN"]
        derived = churn.count_alerts(ordered)
    assert derived == len(fired) == 2


def test_the_tile_figures_are_the_run_rows_figures() -> None:
    with _DB():
        store.insert_spans(
            [
                _span("s0", "", "work", "work", STATE, 100),
                _span("n1", "s0", "qa", "qa", {"progress": "2/5"}, 110),
                _span("t1", "n1", "qa", "agent_turn", dict(TURN), 120),
                _span("t2", "n1", "qa", "agent_turn", {**TURN, "total_cost_usd": 2.0}, 190),
            ]
        )
        row = figures.run_figures("run-1")
        tiles = overview.run_overview("run-1")["figures"]
    assert {key: tiles[key] for key in row} == row
    assert tiles["cost_usd"] == 3.0
    assert (tiles["items_done"], tiles["items_total"]) == (2, 5)
    assert tiles["wall_s"] > 0
    assert tiles["wall_s"] >= tiles["active_s"]


def test_sessions_are_the_distinct_resume_generations() -> None:
    with _DB():
        store.insert_spans(
            [
                _span("s0", "", "work", "work", STATE, 100, generation=1, trace="a"),
                _span("n1", "s0", "qa", "qa", {}, 110, generation=1, trace="a"),
                _span("n2", "s0", "qa", "qa", {}, 400, generation=2, trace="b"),
                _span("n3", "s0", "qa", "qa", {}, 800, generation=2, trace="c"),
            ]
        )
        found = overview.run_overview("run-1")
    assert found["figures"]["sessions"] == 2


def test_a_run_that_never_reported_a_generation_is_one_session() -> None:
    with _DB():
        store.insert_spans([_span("s0", "", "work", "work", STATE, 100), _span("n1", "s0", "qa", "qa", {}, 110)])
        found = overview.run_overview("run-1")
    assert found["figures"]["sessions"] == 1


def test_a_backend_with_no_cost_carries_its_estimate_and_no_dollar_figure() -> None:
    with _DB():
        store.insert_spans(
            [
                _span("s0", "", "work", "work", STATE, 100),
                _span("n1", "s0", "qa", "qa", {}, 110),
                _span(
                    "t1", "n1", "qa", "agent_turn",
                    {"backend": "codex", "model": "gpt-5.5", "duration_ms": 60000, "usage.input_tokens": 1000000, "usage.output_tokens": 100000},
                    120,
                ),
            ]
        )
        tiles = overview.run_overview("run-1")["figures"]
    assert tiles["reports_cost"] is False
    assert tiles["cost_usd"] is None
    assert tiles["backends"] == ["codex"]
    assert tiles["est_usd"] == 5.0 + 3.0


def test_the_overview_endpoint_serves_the_tile_figures_and_the_standing() -> None:
    with _DB():
        store.insert_spans(
            [
                _span("s0", "", "work", "work", STATE, 100),
                _span("n1", "s0", "qa", "qa", {}, 110),
                _span("t1", "n1", "qa", "agent_turn", dict(TURN), 120),
                _span("t2", "n1", "qa", "agent_turn", dict(TURN), 190),
            ]
        )
        with TestClient(app=groom_app.create_app()) as client:
            body = client.get("/api/run/run-1/overview").json()
    assert body["figures"]["turns"] == 2
    assert body["standing"]["retries"] == 1
    assert body["standing"]["problems"] == 1
