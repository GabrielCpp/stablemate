from __future__ import annotations

import asyncio
import tempfile
import threading
from collections.abc import Iterator
from unittest.mock import patch

import pytest
from _native_support import node_active_export

from groom import alerts, live, otlp, projection, sidecar_hub, state
from groom import app as groom_app
from groom.models import RunTelemetry, WorkflowContainer, WorkflowState
from workhorse import control


@pytest.fixture(autouse=True)
def quiet_fleet(monkeypatch) -> Iterator[None]:
    monkeypatch.setenv("GROOM_FLUSH_S", "0.01")
    for registry in (state.WORKFLOWS, state.RUNS, state.WATCHING):
        registry.clear()
    state.CLIENTS.clear()
    sidecar_hub.CONNECTIONS.clear()
    state.SCANNING = False
    live.reset()
    yield
    live.reset()
    state.CLIENTS.clear()
    state.WORKFLOWS.clear()
    state.RUNS.clear()


@pytest.fixture
def dirs() -> Iterator[tuple[str, str]]:
    with tempfile.TemporaryDirectory() as run_dir, tempfile.TemporaryDirectory() as workspace:
        yield run_dir, workspace


async def _ingest(run_id: str, dirs: tuple[str, str], node: str = "review") -> None:
    points = otlp.parse_metrics(node_active_export(run_id, dirs[0], dirs[1], node))
    await groom_app._dispatch_alerts(alerts.ingest_metrics(points))
    await groom_app._project_native_rows(points)


def _drain(queue: asyncio.Queue) -> list[dict]:
    frames = []
    while not queue.empty():
        frames.append(queue.get_nowait())
    return frames


def _tab() -> asyncio.Queue:
    queue = state.new_client_queue()
    state.add_client(queue)
    return queue


def test_a_quiet_fleet_sends_no_frame():
    async def drive():
        live.bind(asyncio.get_running_loop())
        queue = _tab()
        live.snapshot()
        await asyncio.sleep(0.5)
        return _drain(queue)

    assert asyncio.run(drive()) == []


def test_one_metric_batch_sends_one_run_frame_for_its_run(dirs):
    async def drive():
        live.bind(asyncio.get_running_loop())
        await _ingest("run-a", dirs)
        await _ingest("run-b", dirs)
        queue = _tab()
        live.snapshot()
        await _ingest("run-a", dirs, node="deploy")
        await asyncio.sleep(0.2)
        return _drain(queue)

    frames = asyncio.run(drive())
    runs = [f for f in frames if f["type"] == "run"]
    assert [f["run"]["run_id"] for f in runs] == ["run-a"]
    assert runs[0]["run"]["node"] == "deploy"


def test_two_batches_inside_one_window_send_one_run_frame(dirs, monkeypatch):
    monkeypatch.setenv("GROOM_FLUSH_S", "0.2")

    async def drive():
        live.bind(asyncio.get_running_loop())
        await _ingest("run-a", dirs)
        queue = _tab()
        live.snapshot()
        await _ingest("run-a", dirs, node="deploy")
        await _ingest("run-a", dirs, node="verify")
        await asyncio.sleep(0.5)
        return _drain(queue)

    runs = [f for f in asyncio.run(drive()) if f["type"] == "run"]
    assert len(runs) == 1
    assert runs[0]["run"]["node"] == "verify"


def test_a_run_turns_silent_when_its_silence_passes_the_threshold(dirs):
    async def drive():
        live.bind(asyncio.get_running_loop())
        await _ingest("run-a", dirs)
        queue = _tab()
        live.snapshot()
        await asyncio.sleep(1.2)
        return _drain(queue)

    with patch.object(projection, "LIVE_AFTER_S", 0.2):
        frames = asyncio.run(drive())
    runs = [f for f in frames if f["type"] == "run"]
    assert [f["run"]["live"] for f in runs] == ["dead"]


def test_a_row_built_twice_apart_has_the_same_stable_content():
    wf = WorkflowContainer(container_id="abc", name="w", state=WorkflowState.RUNNING, native=True, run_id="run-a")
    tel = RunTelemetry(run_id="run-a", native=True, current_node="review", node_elapsed_s=30.0,
                       first_seen_ts=100.0, last_telemetry_ts=100.0)
    state.RUNS["run-a"] = tel
    first = projection.run_row(wf, tel, now=200.0)
    second = projection.run_row(wf, tel, now=210.0)
    assert first != second
    assert live.stable(first) == live.stable(second)


def test_removing_a_workflow_sends_run_removed():
    state.WORKFLOWS["abc"] = WorkflowContainer(container_id="abc", name="w", state=WorkflowState.RUNNING)

    async def drive():
        live.bind(asyncio.get_running_loop())
        queue = _tab()
        live.snapshot()
        state.WORKFLOWS.pop("abc")
        live.mark_fleet()
        await asyncio.sleep(0.2)
        return _drain(queue)

    frames = asyncio.run(drive())
    assert [(f["type"], f["id"]) for f in frames if f["type"] == "run_removed"] == [("run_removed", "abc")]


def test_versions_only_go_up():
    state.WORKFLOWS["abc"] = WorkflowContainer(container_id="abc", name="w", state=WorkflowState.RUNNING)

    async def drive():
        live.bind(asyncio.get_running_loop())
        queue = _tab()
        live.snapshot()
        state.WORKFLOWS["abc"].current_node = "build"
        live.mark_fleet()
        await asyncio.sleep(0.1)
        state.WORKFLOWS.pop("abc")
        live.mark_fleet()
        await asyncio.sleep(0.1)
        return _drain(queue)

    versions = [f["v"] for f in asyncio.run(drive())]
    assert versions == sorted(set(versions)) and len(versions) >= 2


def test_a_full_queue_gets_a_snapshot_as_its_next_frame():
    state.WORKFLOWS["abc"] = WorkflowContainer(container_id="abc", name="w", state=WorkflowState.RUNNING)

    async def drive():
        queue = _tab()
        for index in range(state.CLIENT_QUEUE_MAX):
            queue.put_nowait({"type": "notify", "message": str(index)})
        state.broadcast_nowait({"type": "notify", "message": "overflow"})
        return _drain(queue)

    frames = asyncio.run(drive())
    assert [f["type"] for f in frames] == ["state"]
    assert [r["id"] for r in frames[0]["runs"]] == ["abc"]


def test_an_overflowed_tab_has_its_open_run_sent_again():
    state.WORKFLOWS["abc"] = WorkflowContainer(container_id="abc", name="w", state=WorkflowState.RUNNING)
    refreshed = []

    async def drive():
        queue = _tab()
        state.watch(queue, "abc")
        for index in range(state.CLIENT_QUEUE_MAX):
            queue.put_nowait({"type": "notify", "message": str(index)})
        state.broadcast_nowait({"type": "notify", "message": "overflow"})

    with patch.object(state, "WATCH_REFRESH", refreshed.append):
        asyncio.run(drive())
    assert refreshed == ["abc"]


def test_a_mark_from_another_thread_produces_a_fleet_meta_frame():
    async def drive():
        live.bind(asyncio.get_running_loop())
        queue = _tab()
        live.snapshot()
        state.SCANNING = True
        worker = threading.Thread(target=live.mark_fleet_threadsafe)
        worker.start()
        worker.join()
        await asyncio.sleep(0.2)
        return _drain(queue)

    frames = asyncio.run(drive())
    assert [f["type"] for f in frames] == ["fleet_meta"]
    assert frames[0]["scanning"] is True


def test_a_mark_from_another_thread_before_bind_does_nothing():
    worker = threading.Thread(target=live.mark_fleet_threadsafe)
    worker.start()
    worker.join()


def test_the_gate_backfill_retries_on_failure_and_marks_the_fleet_on_success(dirs):
    run = RunTelemetry(run_id="run-g", native=True, run_dir=dirs[0], workspace=dirs[1], wait_kind="operator")
    state.RUNS["run-g"] = run
    answers = [None, None, {"ok": True, "questions": [{"path": "docs/a.md", "question": "Which?", "kind": "operator"}]}]
    calls = []

    def reply(*args, **kwargs):
        calls.append(1)
        return answers[len(calls) - 1]

    async def drive():
        live.bind(asyncio.get_running_loop())
        queue = _tab()
        live.snapshot()
        groom_app._ensure_gate_backfill(run)
        await asyncio.wait_for(groom_app._BACKFILLS["run-g"], timeout=3.0)
        await asyncio.sleep(0.2)
        return _drain(queue)

    with patch.object(groom_app, "GATE_BACKFILL_RETRY_S", (0.02, 0.02, 0.02)), \
         patch.object(control, "send", reply):
        frames = asyncio.run(drive())

    assert len(calls) == 3
    assert run.wait_gate_path == "docs/a.md"
    assert any(f["type"] == "run" and f["run"]["gate_path"] == "docs/a.md" for f in frames)
    assert groom_app._BACKFILLS == {}


def test_a_connected_tab_receives_a_ping_each_heartbeat_and_a_feed_does_not(monkeypatch):
    monkeypatch.setenv("GROOM_HEARTBEAT_S", "0.02")
    feed = state.new_client_queue()
    state.add_feed(feed, "run-f")

    async def drive():
        queue = _tab()
        task = asyncio.create_task(groom_app._heartbeat_loop())
        try:
            first = await asyncio.wait_for(queue.get(), timeout=2.0)
            second = await asyncio.wait_for(queue.get(), timeout=2.0)
        finally:
            task.cancel()
        return first, second

    try:
        first, second = asyncio.run(drive())
    finally:
        state.remove_feed(feed)
    assert first == {"type": "ping"}
    assert second == {"type": "ping"}
    assert feed.empty()
