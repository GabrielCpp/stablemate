from __future__ import annotations

import os
import tempfile
from pathlib import Path

from litestar.testing import TestClient

from groom import app as groom_app
from groom import cli, figures, overview, projection, store
from groom.models import WorkflowContainer

RUN = "run-clock"
SONNET = "claude-sonnet-5"
HAIKU = "claude-haiku-5"


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


def span(
    span_id: str,
    trace: str,
    parent: str,
    node: str,
    name: str,
    at: float,
    seconds: float,
    attrs: dict,
    generation: int | None,
    run: str = RUN,
) -> dict:
    return {
        "span_id": span_id, "trace_id": trace, "parent_id": parent, "run_id": run,
        "workflow": "coder", "repo": "acme", "branch": "story/acme-sign-in", "node": node,
        "name": name, "run_dir": f"/workspace/.agents/runs/{run}", "start_ts": at,
        "end_ts": at + seconds, "status": "OK", "attrs": attrs, "resume_generation": generation,
    }


STATE = {"workhorse.span_kind": "state", "workhorse.depth": 0}


def turn(model: str, seconds: float, cost: float | None, tokens: dict | None = None) -> dict:
    attrs = {"backend": "claude", "model": model, "duration_ms": seconds * 1000, "usage.output_tokens": 100}
    if cost is not None:
        attrs["total_cost_usd"] = cost
    return {**attrs, **(tokens or {})}


def three_sessions(base: float, run: str = RUN) -> list[dict]:
    cache = {"usage.input_tokens": 10, "usage.cache_read_input_tokens": 900, "usage.cache_creation_input_tokens": 90}
    wait = {"workhorse.span_kind": "wait", "workhorse.wait_kind": "operator"}
    return [
        span("r1", "t1", "", "coder", "run:coder", base, 1000, {"workhorse.terminal": "interrupted"}, 1, run),
        span("s1", "t1", "r1", "work", "work", base + 5, 895, STATE, 1, run),
        span("n1", "t1", "s1", "dev", "dev", base + 10, 300, {"workhorse.depth": 1}, 1, run),
        span("a1", "t1", "n1", "dev", "agent_turn", base + 10, 120, turn(SONNET, 120, 2.0, cache), 1, run),
        span("a2", "t1", "n1", "dev", "agent_turn", base + 140, 60, turn(HAIKU, 60, None), 1, run),
        span("d1", "t1", "s1", "lint", "lint", base + 310, 30, {}, 1, run),
        span("i1", "t1", "s1", "boot", "boot", base + 350, 20, {"workhorse.span_kind": "infra"}, 1, run),
        span("w1", "t1", "s1", "await_operator", "await_operator", base + 400, 100, wait, 1, run),
        span("s2", "t2", "", "work", "work", base + 1500, 200, STATE, 2, run),
        span("n2", "t2", "s2", "dev", "dev", base + 1505, 150, {"workhorse.depth": 1}, 2, run),
        span("a3", "t2", "n2", "dev", "agent_turn", base + 1510, 100, turn(SONNET, 100, 1.5), 2, run),
        span("s3", "t3", "", "work", "work", base + 2000, 200, STATE, 3, run),
        span("n3", "t3", "s3", "dev", "dev", base + 2005, 150, {"workhorse.depth": 1}, 3, run),
        span("a4", "t3", "n3", "dev", "agent_turn", base + 2010, 80, turn(HAIKU, 80, None), 3, run),
    ]


def test_the_wall_clock_segments_sum_to_the_wall_time_and_the_active_ones_to_the_active_tile() -> None:
    with _DB():
        store.insert_spans(three_sessions(1000.0))
        result = overview.run_overview(RUN)
    clock = result["clock"]
    parts = ("agent", "deterministic", "infra", "wait", "unclassified", "resume_gap")
    assert abs(sum(clock[key] for key in parts) - clock["wall"]) < 1e-6
    assert abs(clock["wall"] - result["figures"]["wall_s"]) < 1e-6
    active = clock["agent"] + clock["deterministic"] + clock["infra"]
    assert abs(active - result["figures"]["active_s"]) < 1e-6
    assert (clock["agent"], clock["deterministic"], clock["infra"], clock["wait"]) == (360, 30, 20, 100)
    assert clock["resume_gap"] == 800


def test_the_model_totals_equal_the_cost_report_and_an_unpriced_model_has_no_cost() -> None:
    with _DB():
        store.insert_spans(three_sessions(1000.0))
        models = {row["model"]: row for row in overview.run_overview(RUN)["models"]}
        report = store.node_costs(run=RUN, limit=1000)
    assert abs(sum(row["cost_usd"] or 0.0 for row in models.values()) - sum(row["cost_usd"] or 0.0 for row in report)) < 1e-9
    assert sum(row["turns"] for row in models.values()) == sum(row["turns"] for row in report) == 4
    assert models[SONNET]["cost_usd"] == 3.5
    assert models[HAIKU]["cost_usd"] is None
    assert models[HAIKU]["turns"] == 2
    assert models[SONNET]["output_tokens"] == 200
    assert round(models[SONNET]["cache_read_share"], 2) == 0.9


def test_a_model_with_some_priced_turns_says_how_many() -> None:
    spans = [
        span("r", "t", "", "coder", "run:coder", 1000, 500, {}, 1),
        span("s", "t", "r", "work", "work", 1005, 400, STATE, 1),
        span("n", "t", "s", "dev", "dev", 1010, 300, {"workhorse.depth": 1}, 1),
        span("a", "t", "n", "dev", "agent_turn", 1010, 60, turn(SONNET, 60, 1.0), 1),
        span("b", "t", "n", "dev", "agent_turn", 1100, 60, turn(SONNET, 60, None), 1),
        span("c", "t", "n", "dev", "agent_turn", 1200, 60, {"backend": "claude", "duration_ms": 60000}, 1),
    ]
    with _DB():
        store.insert_spans(spans)
        models = {row["model"]: row for row in overview.run_overview(RUN)["models"]}
    assert models[SONNET]["cost_usd"] == 1.0
    assert (models[SONNET]["cost_turns"], models[SONNET]["turns"]) == (1, 2)
    assert models["(no model recorded)"]["cost_usd"] is None


def test_the_session_rows_are_the_sessions_the_tile_counts() -> None:
    plain = [
        span("r", "t", "", "coder", "run:coder", 1000, 500, {}, None),
        span("s", "t", "r", "work", "work", 1005, 400, STATE, None),
    ]
    with _DB():
        store.insert_spans(three_sessions(1000.0))
        many = overview.run_overview(RUN)
    with _DB():
        store.insert_spans(plain)
        none = overview.run_overview(RUN)
    with _DB():
        empty = overview.run_overview(RUN)
    assert len(many["sessions"]) == many["figures"]["sessions"] == 3
    assert len(none["sessions"]) == none["figures"]["sessions"] == 1
    assert len(empty["sessions"]) == empty["figures"]["sessions"] == 0


def test_a_session_with_no_root_span_has_no_recorded_ending_and_each_gap_is_measured() -> None:
    with _DB():
        store.insert_spans(three_sessions(1000.0))
        rows = overview.run_overview(RUN)["sessions"]
    assert rows[0]["ended"] == {"terminal": "interrupted", "error_class": "", "error_kind": "", "message": ""}
    assert rows[1]["ended"] is None
    assert rows[2]["ended"] is None
    assert [row["gap_s"] for row in rows] == [500, 300, None]
    assert rows[0]["active_s"] == 230
    assert [row["start_ts"] for row in rows] == [1000, 2500, 3000]


def test_the_facts_come_from_the_runs_spans() -> None:
    with _DB():
        store.insert_spans(three_sessions(1000.0))
        facts = overview.run_overview(RUN)["facts"]
    assert facts == {"started_ts": 1000, "branch": "story/acme-sign-in", "run_dir": f"/workspace/.agents/runs/{RUN}"}


def test_the_sections_read_through_the_overview_endpoint() -> None:
    with _DB():
        store.insert_spans(three_sessions(1000.0))
        with TestClient(app=groom_app.create_app()) as client:
            body = client.get(f"/api/run/{RUN}/overview").json()
    assert set(body) >= {"clock", "models", "sessions", "facts"}
    assert len(body["sessions"]) == 3


def test_the_overview_and_the_profile_report_read_one_profile() -> None:
    with _DB():
        store.insert_spans(three_sessions(1000.0))
        costs, profile, progress = figures.read(RUN)
        result = overview.run_overview(RUN)
    assert profile is not None
    assert result["clock"] == profile["time_s"]
    assert result["models"] == profile["models"]
    assert result["sessions"] == profile["session_rows"]
    assert costs["usd"] == 3.5
    assert progress is None


def test_the_profile_report_prints_the_models_and_the_sessions_in_words() -> None:
    with _DB():
        store.insert_spans(three_sessions(1000.0))
        text = cli._format_profile(store.run_profile(RUN))
    assert f"{HAIKU}  turns=2  cost=not reported" in text
    assert f"{SONNET}  turns=2  cost=$3.50" in text
    assert "ended=interrupted" in text
    assert text.count("ended=no recorded ending") == 2


def test_the_run_head_carries_a_checkout_path_for_a_native_run_only() -> None:
    native = WorkflowContainer(container_id="a1", name="n", native=True, workspace_volume="/home/acme/work/api-service")
    docker = WorkflowContainer(container_id="b2", name="d", native=False, workspace_volume="volume-name")
    assert projection.head(native)["checkout"] == "/home/acme/work/api-service"
    assert projection.head(docker)["checkout"] == ""
