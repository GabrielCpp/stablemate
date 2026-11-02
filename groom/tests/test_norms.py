"""The strip above the Overview: a node's norm from successful runs, and the strip's timestamps."""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from groom import alerts, norms, pools, projection, state, store
from groom import app as groom_app
from groom.models import RunTelemetry, WorkflowContainer, WorkflowState


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


def _span(span_id: str, run: str, node: str, name: str, seconds: float, attrs: dict | None = None, workflow: str = "coder") -> dict:
    return {
        "span_id": span_id, "trace_id": run, "parent_id": "", "run_id": run, "workflow": workflow,
        "repo": "acme", "branch": "main", "node": node, "name": name, "run_dir": "",
        "start_ts": 1000.0, "end_ts": 1000.0 + seconds, "status": "OK", "attrs": attrs or {},
    }


def _run(run: str, terminal: str, turns: tuple[float, ...] = (), steps: tuple[float, ...] = (), workflow: str = "coder") -> list[dict]:
    spans = [_span(f"{run}-root", run, f"run:{workflow}", f"run:{workflow}", 900, {"workhorse.terminal": terminal}, workflow)]
    for index, seconds in enumerate(turns):
        spans.append(_span(f"{run}-t{index}", run, "qa", "agent_turn", seconds, {"duration_ms": seconds * 1000}, workflow))
    for index, seconds in enumerate(steps):
        spans.append(_span(f"{run}-s{index}", run, "gate", "gate", seconds, None, workflow))
    return spans


def _seed_history() -> None:
    spans: list[dict] = []
    for index, minutes in enumerate((10, 20, 30, 40, 50)):
        spans += _run(f"ok{index}", "terminal", turns=(minutes * 60.0,), steps=(float(minutes),))
    spans += _run("failed", "fail", turns=(9000.0,), steps=(900.0,))
    spans += _run("paused", "interrupted", turns=(9000.0,))
    spans += _run("other", "terminal", turns=(9000.0,), workflow="author")
    store.insert_spans(spans)


def test_the_norm_is_the_median_over_successful_runs_of_the_same_workflow() -> None:
    with _DB():
        _seed_history()
        found = store.node_norms("coder", "qa")
    assert found["turn"] == {"median_s": 1800.0, "runs": 5}


def test_a_failed_interrupted_or_other_workflow_run_does_not_move_the_norm() -> None:
    with _DB():
        _seed_history()
        before = store.node_norms("coder", "qa")
        store.insert_spans(_run("late-fail", "fail", turns=(90000.0,)) + _run("late-author", "terminal", turns=(90000.0,), workflow="author"))
        after = store.node_norms("coder", "qa")
    assert before == after


def test_a_deterministic_step_has_its_own_norm() -> None:
    with _DB():
        _seed_history()
        found = store.node_norms("coder", "gate")
    assert found["step"] == {"median_s": 30.0, "runs": 5}
    assert found["turn"]["runs"] == 0


def test_a_node_with_agent_turns_in_a_run_gives_that_run_no_step_sample() -> None:
    with _DB():
        _seed_history()
        found = store.node_norms("coder", "qa")
    assert found["step"]["runs"] == 0


def test_the_median_is_blank_under_five_comparable_runs() -> None:
    with _DB():
        store.insert_spans(_run("a", "terminal", turns=(60.0,)) + _run("b", "terminal", turns=(120.0,)) + _run("c", "terminal", turns=(180.0,)))
        found = store.node_norms("coder", "qa")
    assert norms.reading(found["turn"]) == {"median_s": None, "runs": 3}


def test_a_node_nobody_has_run_has_no_runs() -> None:
    with _DB():
        _seed_history()
        found = store.node_norms("coder", "never-ran")
    assert found["turn"] == {"median_s": None, "runs": 0}
    assert found["step"] == {"median_s": None, "runs": 0}


def _wf() -> WorkflowContainer:
    return WorkflowContainer(
        container_id="c1", name="coder-acme", workflow_type="coder", run_id="r1",
        state=WorkflowState.RUNNING, native=True,
    )


def _feed(points: list[tuple[str, float, dict]], now: float) -> RunTelemetry:
    alerts.ingest_metrics(
        [{"run_id": "r1", "name": name, "ts": now, "value": value, "attrs": {"node": "qa", **attrs}} for name, value, attrs in points],
        now=now,
    )
    return state.RUNS["r1"]


@pytest.fixture(autouse=True)
def _clean_runs():
    state.RUNS.pop("r1", None)
    yield
    state.RUNS.pop("r1", None)


def test_an_agent_turn_is_timed_from_the_turn_not_the_node() -> None:
    norms.reset()
    norms.CACHE[("coder", "qa")] = {"turn": {"median_s": 1980.0, "runs": 23}, "step": {"median_s": None, "runs": 0}}
    tel = _feed([
        ("workhorse.run.heartbeat", 1.0, {}),
        ("workhorse.node.active", 1.0, {}),
        ("workhorse.node.elapsed_s", 900.0, {}),
        ("workhorse.turn.active", 1.0, {}),
        ("workhorse.turn.elapsed_s", 799.0, {}),
        ("workhorse.turn.idle_s", 1.0, {}),
    ], now=5000.0)
    tel.workflow = "coder"
    strip = projection.running_strip(_wf(), tel, None, now=5010.0)
    assert strip is not None
    assert strip["kind"] == "turn"
    assert strip["started_ts"] == 5000.0 - 799.0
    assert strip["idle_since_ts"] == 4999.0
    assert strip["beat_ts"] == tel.last_heartbeat_ts
    assert strip["norm"] == {"median_s": 1980.0, "runs": 23}
    norms.reset()


def test_a_wait_on_the_operator_has_no_norm_and_counts_the_wait() -> None:
    norms.reset()
    norms.CACHE[("coder", "qa")] = {"turn": {"median_s": 60.0, "runs": 9}, "step": {"median_s": 60.0, "runs": 9}}
    tel = _feed([
        ("workhorse.node.active", 1.0, {}),
        ("workhorse.wait.active", 1.0, {"wait_kind": "operator"}),
        ("workhorse.wait.elapsed_s", 720.0, {"wait_kind": "operator"}),
    ], now=5000.0)
    strip = projection.running_strip(_wf(), tel, None, now=5000.0)
    assert strip is not None
    assert (strip["kind"], strip["wait_kind"], strip["norm"]) == ("wait", "operator", None)
    assert strip["started_ts"] == 5000.0 - 720.0
    norms.reset()


def test_a_node_with_no_turn_running_is_a_step_against_the_step_norm() -> None:
    norms.reset()
    norms.CACHE[("coder", "qa")] = {"turn": {"median_s": 60.0, "runs": 9}, "step": {"median_s": 110.0, "runs": 6}, "node": {"kind": "step"}}
    tel = _feed([
        ("workhorse.node.active", 1.0, {}),
        ("workhorse.node.elapsed_s", 124.0, {}),
    ], now=5000.0)
    strip = projection.running_strip(_wf(), tel, None, now=5000.0)
    assert strip is not None
    assert strip["kind"] == "step"
    assert strip["idle_since_ts"] is None
    assert strip["started_ts"] == 5000.0 - 124.0
    assert strip["norm"] == {"median_s": 110.0, "runs": 6}
    norms.reset()


def test_an_agent_node_between_turns_is_not_called_a_step_and_keeps_the_turn_norm() -> None:
    norms.reset()
    norms.CACHE[("coder", "qa")] = {"turn": {"median_s": 60.0, "runs": 9}, "step": {"median_s": None, "runs": 0}, "node": {"kind": "agent"}}
    tel = _feed([("workhorse.node.active", 1.0, {}), ("workhorse.node.elapsed_s", 124.0, {})], now=5000.0)
    strip = projection.running_strip(_wf(), tel, None, now=5000.0)
    assert strip is not None
    assert (strip["kind"], strip["idle_since_ts"], strip["norm"]) == ("between", None, {"median_s": 60.0, "runs": 9})
    norms.reset()


def test_a_node_never_finished_anywhere_is_neither_a_step_nor_an_agent() -> None:
    norms.reset()
    norms.CACHE[("coder", "qa")] = {"turn": {"median_s": None, "runs": 0}, "step": {"median_s": None, "runs": 0}, "node": {"kind": None}}
    tel = _feed([("workhorse.node.active", 1.0, {}), ("workhorse.node.elapsed_s", 5.0, {})], now=5000.0)
    strip = projection.running_strip(_wf(), tel, None, now=5000.0)
    assert strip is not None
    assert (strip["kind"], strip["norm"]) == ("node", {"median_s": None, "runs": 0})
    norms.reset()


def test_a_norm_not_read_yet_is_none_and_a_sparse_one_carries_only_its_count() -> None:
    norms.reset()
    tel = _feed([("workhorse.node.active", 1.0, {}), ("workhorse.node.elapsed_s", 5.0, {})], now=5000.0)
    strip = projection.running_strip(_wf(), tel, None, now=5000.0)
    assert strip is not None and strip["norm"] is None
    norms.CACHE[("coder", "qa")] = {"turn": {"median_s": 1.0, "runs": 4}, "step": {"median_s": 90.0, "runs": 4}, "node": {"kind": "step"}}
    strip = projection.running_strip(_wf(), tel, None, now=5000.0)
    assert strip is not None and strip["norm"] == {"median_s": None, "runs": 4}
    norms.reset()


def test_rendering_the_strip_never_reads_the_store(monkeypatch: pytest.MonkeyPatch) -> None:
    norms.reset()
    norms.CACHE[("coder", "qa")] = {"turn": {"median_s": 1.0, "runs": 9}, "step": {"median_s": 1.0, "runs": 9}}

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("the strip read the store")

    monkeypatch.setattr(store, "node_norms", forbidden)
    tel = _feed([("workhorse.node.active", 1.0, {}), ("workhorse.node.elapsed_s", 5.0, {})], now=5000.0)
    for _ in range(20):
        projection.run_detail(_wf(), tel, None, now=5001.0)
    norms.reset()


def test_the_store_is_read_once_per_node_and_again_only_when_the_run_moves(monkeypatch: pytest.MonkeyPatch) -> None:
    norms.reset()
    reads: list[tuple[str, str]] = []

    def counting(workflow: str, node: str) -> dict:
        reads.append((workflow, node))
        return {"turn": {"median_s": 10.0, "runs": 7}, "step": {"median_s": 10.0, "runs": 7}}

    monkeypatch.setattr(store, "node_norms", counting)
    pushed: list[str] = []

    async def record(container_id: str) -> None:
        pushed.append(container_id)

    monkeypatch.setattr(groom_app, "_push_detail", record)
    tel = RunTelemetry(run_id="r1", workflow="coder", current_node="qa")
    wf = _wf()

    async def settle() -> None:
        await asyncio.sleep(0.2)

    async def scenario() -> None:
        for _ in range(30):
            groom_app._queue_norms(wf, tel)
        await settle()
        assert reads == [("coder", "qa")]
        assert pushed == ["c1"]
        for _ in range(30):
            groom_app._queue_norms(wf, tel)
        await settle()
        assert reads == [("coder", "qa")]
        tel.current_node = "dev-build"
        for _ in range(30):
            groom_app._queue_norms(wf, tel)
        await settle()
        assert reads == [("coder", "qa"), ("coder", "dev-build")]
        tel.current_node = "qa"
        groom_app._queue_norms(wf, tel)
        await settle()
        assert reads == [("coder", "qa"), ("coder", "dev-build"), ("coder", "qa")]

    try:
        asyncio.run(scenario())
    finally:
        pools.shutdown_all()
        norms.reset()
