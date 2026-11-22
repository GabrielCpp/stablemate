from __future__ import annotations

import asyncio
import json
import tempfile
import threading
import time
from pathlib import Path
from collections.abc import Iterator
from unittest.mock import patch

import pytest
import _tui_support as support
from _native_support import node_active_export

from groom import alerts, live, otlp, projection, sidecar_hub, state, store
from groom import app as groom_app
from groom.models import RunTelemetry, WorkflowContainer, WorkflowState
from workhorse import control


@pytest.fixture(autouse=True)
def quiet_fleet(monkeypatch, tmp_path) -> Iterator[None]:
    monkeypatch.setenv("GROOM_FLUSH_S", "0.01")
    monkeypatch.setenv("GROOM_DB", str(tmp_path / "groom.db"))
    store.reset()
    state.HISTORIES.clear()
    state.TRANSCRIPT_TASKS.clear()
    for registry in (state.WORKFLOWS, state.RUNS, state.WATCHING):
        registry.clear()
    state.CLIENTS.clear()
    sidecar_hub.CONNECTIONS.clear()
    state.SCANNING = False
    live.reset()
    yield
    live.reset()
    store.reset()
    state.HISTORIES.clear()
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


def test_two_batches_a_window_apart_send_one_run_frame_in_total(dirs):
    async def drive():
        live.bind(asyncio.get_running_loop())
        queue = _tab()
        live.snapshot()
        await _ingest("run-a", dirs)
        await asyncio.sleep(0.2)
        await _ingest("run-a", dirs)
        await asyncio.sleep(0.2)
        return _drain(queue)

    runs = [f for f in asyncio.run(drive()) if f["type"] == "run"]
    assert len(runs) == 1


def _health(monkeypatch, **overrides) -> dict:
    health = {
        "ok": True,
        "last_ok_ts": 1.0,
        "last_write_ts": 1.0,
        "last_prune_ts": 1.0,
        "wal_bytes": 10,
        **overrides,
    }
    monkeypatch.setattr(projection.store, "health_dict", lambda: dict(health))
    return health


def test_a_store_write_alone_sends_no_fleet_meta(monkeypatch):
    _health(monkeypatch)

    async def drive():
        live.bind(asyncio.get_running_loop())
        queue = _tab()
        live.snapshot()
        _health(monkeypatch, last_ok_ts=2.0, last_write_ts=2.0, last_prune_ts=2.0, wal_bytes=99)
        live.mark_fleet()
        await asyncio.sleep(0.2)
        return _drain(queue)

    assert asyncio.run(drive()) == []


def test_a_change_to_store_ok_sends_fleet_meta_with_the_whole_store(monkeypatch):
    _health(monkeypatch)

    async def drive():
        live.bind(asyncio.get_running_loop())
        queue = _tab()
        live.snapshot()
        _health(monkeypatch, ok=False, wal_bytes=99)
        live.mark_fleet()
        await asyncio.sleep(0.2)
        return _drain(queue)

    frames = asyncio.run(drive())
    assert [f["type"] for f in frames] == ["fleet_meta"]
    assert frames[0]["store"]["ok"] is False
    assert frames[0]["store"]["wal_bytes"] == 99


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


def _watched(run_id: str = "run-w", **fields) -> WorkflowContainer:
    wf = WorkflowContainer(container_id=run_id, name="w", state=WorkflowState.RUNNING, run_id=run_id, **fields)
    state.WORKFLOWS[run_id] = wf
    return wf


async def _open(run_id: str = "run-w") -> asyncio.Queue:
    queue = _tab()
    await groom_app._handle_command({"cmd": "watch", "run_id": run_id}, queue)
    return queue


async def _log(run_id: str, body: str) -> None:
    rows = [{"run_id": run_id, "body": body, "ts": time.time()}]
    await groom_app._store_history_batch(rows, store.insert_logs, kind="logs")
    await groom_app._push_received(rows)


def _details(frames: list[dict]) -> list[dict]:
    return [f for f in frames if f["type"] == "detail"]


def test_a_quiet_watched_run_gets_no_detail_after_the_first():
    _watched()

    async def drive():
        live.bind(asyncio.get_running_loop())
        queue = await _open()
        first = _drain(queue)
        live.snapshot()
        await asyncio.sleep(0.5)
        return first, _drain(queue)

    first, rest = asyncio.run(drive())
    assert len(_details(first)) == 1
    assert rest == []


def test_one_log_batch_raises_activity_rev_by_one_and_sends_one_detail():
    _watched()

    async def drive():
        live.bind(asyncio.get_running_loop())
        queue = await _open()
        opened = _details(_drain(queue))[0]["detail"]["activity_rev"]
        live.snapshot()
        await _log("run-w", "one")
        await asyncio.sleep(0.2)
        return opened, _details(_drain(queue))

    opened, sent = asyncio.run(drive())
    assert len(sent) == 1
    assert sent[0]["detail"]["activity_rev"] == opened + 1


def test_two_log_batches_inside_one_window_send_one_detail(monkeypatch):
    _watched()
    monkeypatch.setenv("GROOM_FLUSH_S", "0.2")

    async def drive():
        live.bind(asyncio.get_running_loop())
        queue = await _open()
        _drain(queue)
        live.snapshot()
        await _log("run-w", "one")
        await _log("run-w", "two")
        await asyncio.sleep(0.6)
        return _details(_drain(queue))

    sent = asyncio.run(drive())
    assert len(sent) == 1
    assert [line["body"] for line in sent[0]["detail"]["logs"]] == ["two", "one"]


def test_watch_sends_a_detail_at_once_even_when_the_same_one_went_out():
    _watched()

    async def drive():
        live.bind(asyncio.get_running_loop())
        first = await _open()
        second = _tab()
        await groom_app._handle_command({"cmd": "watch", "run_id": "run-w"}, second)
        return _details(_drain(first)), _details(_drain(second))

    first, second = asyncio.run(drive())
    assert len(first) == 1
    assert len(second) == 1


def test_a_tab_that_just_opened_a_run_does_not_make_the_others_repeat_it():
    _watched()

    async def drive():
        live.bind(asyncio.get_running_loop())
        first = await _open()
        _drain(first)
        second = _tab()
        await groom_app._handle_command({"cmd": "watch", "run_id": "run-w"}, second)
        await asyncio.sleep(0.2)
        return _drain(first), _drain(second)

    first, second = asyncio.run(drive())
    assert first == []
    assert len(_details(second)) == 1


def test_a_flush_sends_the_fleet_frames_before_the_details(dirs):
    _watched("run-a")

    async def drive():
        live.bind(asyncio.get_running_loop())
        queue = await _open("run-a")
        _drain(queue)
        live.snapshot()
        await _log("run-a", "one")
        state.WORKFLOWS["run-a"].current_node = "build"
        live.mark_fleet()
        await asyncio.sleep(0.3)
        return [f["type"] for f in _drain(queue)]

    assert asyncio.run(drive()) == ["run", "detail"]


def _line(text: str, ts: float) -> str:
    update = {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": text}}
    return json.dumps({"sessionId": "s", "update": update, "_meta": {"ts": ts, "node": "implement"}}) + "\n"


def _native(tmp_path) -> tuple[WorkflowContainer, Path]:
    live_dir = tmp_path / "transcripts" / "live"
    live_dir.mkdir(parents=True)
    path = live_dir / "001-00001-implement.jsonl"
    path.write_text(_line("first", 10.0))
    return _watched(native=True, runs_volume=str(tmp_path)), path


def test_a_transcript_line_reaches_the_open_run_within_a_second(tmp_path):
    _, path = _native(tmp_path)

    async def drive():
        live.bind(asyncio.get_running_loop())
        queue = await _open()
        opened = _details(_drain(queue))[0]["detail"]["activity_rev"]
        await asyncio.sleep(0.3)
        with path.open("a") as handle:
            handle.write(_line("second", 11.0))
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            await asyncio.sleep(0.05)
            sent = _details(_drain(queue))
            if sent:
                return opened, sent[-1]["detail"]["activity_rev"]
        return opened, None

    opened, after = asyncio.run(drive())
    assert after is not None and after > opened


def test_releasing_the_last_watcher_cancels_the_transcript_task(tmp_path):
    _native(tmp_path)

    async def drive():
        live.bind(asyncio.get_running_loop())
        queue = await _open()
        task = state.TRANSCRIPT_TASKS["run-w"]
        state.remove_client(queue)
        await asyncio.sleep(0.1)
        return task, dict(state.TRANSCRIPT_TASKS)

    task, tasks = asyncio.run(drive())
    assert task.cancelled() or task.done()
    assert tasks == {}


def test_a_detail_built_twice_apart_is_the_same_but_for_its_timestamp():
    wf = WorkflowContainer(container_id="abc", name="w", state=WorkflowState.RUNNING, native=True, run_id="run-a")
    tel = RunTelemetry(run_id="run-a", native=True, current_node="review", node_elapsed_s=30.0,
                       first_seen_ts=100.0, last_telemetry_ts=100.0)
    state.RUNS["run-a"] = tel
    history = [
        support.log_row(100.0, "compiled"),
        support.transcript_row(140.0, support.message_update("agent_message_chunk", "done"), "001-implement"),
    ]
    first = projection.run_detail(wf, tel, now=200.0, history=history)
    second = projection.run_detail(wf, tel, now=210.0, history=history)
    for detail in (first, second):
        detail.pop("ts", None)
    assert first == second


class _HeldProc:
    pid = 4242

    def __init__(self) -> None:
        self.done = threading.Event()

    def wait(self) -> int:
        self.done.wait(5.0)
        return 0


@pytest.fixture
def queue_config(monkeypatch, tmp_path):
    from groom import dispatch, dispatch_ledger

    monkeypatch.setenv("STABLEMATE_CONFIG", str(tmp_path / "config.toml"))
    (tmp_path / "config.toml").write_text('[groom.dispatch.q]\ncommand = "workhorse-loop-runner"\nconcurrency = 1\n')
    dispatch.reset()
    yield dispatch, dispatch_ledger
    dispatch.reset()


def _metas(frames: list[dict]) -> list[dict]:
    return [frame for frame in frames if frame["type"] == "fleet_meta"]


def test_a_dispatch_enqueue_sends_one_fleet_meta_with_the_dispatch_revision_one_higher(queue_config, monkeypatch):
    dispatch, _ = queue_config
    monkeypatch.setattr(dispatch, "_drain", lambda queue: None)

    async def drive():
        live.bind(asyncio.get_running_loop())
        queue = _tab()
        before = live.snapshot()["revs"]["dispatch"]
        await asyncio.to_thread(dispatch.enqueue, "q")
        await asyncio.sleep(0.2)
        return before, _drain(queue)

    before, frames = asyncio.run(drive())
    assert [f["type"] for f in frames] == ["fleet_meta"]
    assert frames[0]["revs"]["dispatch"] == before + 1


def test_a_dispatch_finish_from_a_thread_sends_a_fleet_meta_with_a_higher_revision(queue_config, monkeypatch):
    dispatch, ledger = queue_config
    proc = _HeldProc()
    monkeypatch.setattr(dispatch, "_launch", lambda item_id, command, params: proc)

    async def drive():
        live.bind(asyncio.get_running_loop())
        queue = _tab()
        item = await asyncio.to_thread(dispatch.enqueue, "q")
        await asyncio.sleep(0.2)
        started = _metas(_drain(queue))[-1]["revs"]["dispatch"]
        proc.done.set()
        await asyncio.sleep(0.3)
        return item, started, _drain(queue)

    item, started, frames = asyncio.run(drive())
    assert ledger.dispatch_get(item["item_id"])["status"] == ledger.DISPATCH_DONE
    assert [f["revs"]["dispatch"] for f in _metas(frames)] == [started + 1]


def test_a_written_summary_sends_a_fleet_meta_with_a_higher_history_revision():
    async def drive():
        live.bind(asyncio.get_running_loop())
        queue = _tab()
        before = live.snapshot()["revs"]["history"]
        with patch.object(groom_app.history, "compute", lambda run_id: None):
            await groom_app._write_summary("run-s")
        await asyncio.sleep(0.2)
        return before, _drain(queue)

    before, frames = asyncio.run(drive())
    assert [f["type"] for f in frames] == ["summary", "fleet_meta"]
    assert frames[1]["revs"]["history"] == before + 1


def test_a_summary_pass_that_archives_a_run_sends_a_higher_history_revision_and_one_with_nothing_sends_none():
    async def drive(archives: list[str]):
        live.reset()
        live.bind(asyncio.get_running_loop())
        queue = _tab()
        before = live.snapshot()["revs"]["history"]
        with (
            patch.object(groom_app.history, "discover", lambda: []),
            patch.object(groom_app.history, "discover_archives", lambda: archives),
            patch.object(groom_app.history, "compute_archive", lambda run_id: True),
            patch.object(groom_app, "SUMMARY_PAUSE_S", 0),
        ):
            await groom_app._summary_pass()
        await asyncio.sleep(0.2)
        return before, _drain(queue)

    before, frames = asyncio.run(drive(["run-a"]))
    assert [f["revs"]["history"] for f in _metas(frames)] == [before + 2]
    _, frames = asyncio.run(drive([]))
    assert frames == []
