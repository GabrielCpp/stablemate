"""A waiter must see existing conditions, not only the next alert edge."""
from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Thread

import pytest
from litestar import Litestar
from litestar.testing import TestClient
from websockets.sync.server import ServerConnection, serve

from groom import cli, projection, state, store
from groom import app as groom_app
from groom.alerts import Alert
from groom.attention import AttentionEvent, DigestFrame, EventFrame, Standing, Window
from groom.models import GateInfo, RunTelemetry, WorkflowContainer


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.setenv("GROOM_DB", str(tmp_path / "groom.db"))
    monkeypatch.setattr(state, "RUNS", {})
    monkeypatch.setattr(state, "WORKFLOWS", {})
    monkeypatch.setattr(state, "CLIENTS", set())
    monkeypatch.setattr(state, "WATCHING", {})
    monkeypatch.setattr(state, "FEEDS", {})
    monkeypatch.setattr(state, "EVENTS", {})
    store.reset()
    yield
    store.reset()


def event_frame(event: AttentionEvent, seq: int = 1) -> dict:
    return EventFrame(seq=seq, ts=1.0, event=event).model_dump()


def digest_frame(seq: int = 1) -> dict:
    return DigestFrame(
        seq=seq, ts=2.0, since=0.0, until=2.0, quiet=True, summary="quiet",
        standing=Standing(), window=Window(),
    ).model_dump()


def current_frames() -> list[dict]:
    return [event_frame(event, seq) for seq, event in enumerate(projection.attention_events([]), 1)]


@contextmanager
def frame_server(frames: list[dict]) -> Iterator[str]:
    def handler(socket: ServerConnection) -> None:
        for frame in frames:
            socket.send(json.dumps(frame))
        socket.close()

    with serve(handler, "127.0.0.1", 0) as server:
        worker = Thread(target=server.serve_forever)
        worker.start()
        try:
            yield f"http://127.0.0.1:{server.socket.getsockname()[1]}"
        finally:
            server.shutdown()
            worker.join(timeout=5)


def test_wait_command_is_available(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["wait", "--help"])
    assert exit_info.value.code == 0
    assert "--until" in capsys.readouterr().out


def test_initial_snapshot_includes_blocked_run_without_fleet_row(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("GROOM_DB", str(tmp_path / "groom.db"))
    monkeypatch.setattr(state, "RUNS", {
        "acme": RunTelemetry(run_id="acme", wait_kind="operator",
                             wait_gate_question="Proceed?", current_node="review"),
    })
    store.reset()
    try:
        snapshot = projection.state_message([])
        assert snapshot["attention"][0]["event"] == "blocked"
        assert snapshot["attention"][0]["question"] == "Proceed?"
    finally:
        store.reset()


@pytest.mark.parametrize("kind", ["machine", "cap", "retry", ""])
def test_expected_waits_do_not_wake_monitor(kind: str) -> None:
    state.RUNS["acme"] = RunTelemetry(run_id="acme", wait_kind=kind)
    assert projection.state_message([])["attention"] == []


def test_legacy_sidecar_gate_uses_run_identity() -> None:
    wf = WorkflowContainer(container_id="container", name="coder", run_id="acme")
    wf.gates["gate.md"] = GateInfo(workflow_id="container", file_path="gate.md", question="Proceed?")
    event = projection.attention_events([wf])[0]
    assert event.run_id == "acme"
    assert event.question == "Proceed?"


@pytest.mark.parametrize("rule,event_name", [
    ("STUCK", "stuck"), ("STALL", "stalled"), ("GAVE-UP", "gave-up"),
])
def test_default_filter_returns_existing_alert(
    rule: str, event_name: str, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    state.RUNS["acme"] = RunTelemetry(run_id="acme", fired={rule})
    with frame_server(current_frames()) as url:
        monkeypatch.setenv("GROOM_URL", url)
        cli.main(["wait", "--run", "acme"])
    assert f"acme: {event_name}" in capsys.readouterr().out


def test_connection_closing_after_healthy_snapshot_is_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    with frame_server([digest_frame()]) as url:
        monkeypatch.setenv("GROOM_URL", url)
        with pytest.raises(SystemExit) as exit_info:
            cli.main(["wait", "--run", "acme", "--json"])
    assert exit_info.value.code == 1
    assert capsys.readouterr().out == ""


def test_digest_frame_does_not_wake_wait(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    state.RUNS["acme"] = RunTelemetry(run_id="acme", terminal="failed", current_node="build")
    frames = [digest_frame(1), *current_frames()]
    frames[1]["seq"] = 2
    with frame_server(frames) as url:
        monkeypatch.setenv("GROOM_URL", url)
        cli.main(["wait", "--run", "acme", "--json"])
    assert json.loads(capsys.readouterr().out)["event"] == "ended"


def test_cli_ignores_other_runs_and_unselected_events(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    frames = [
        event_frame(AttentionEvent(run_id="globex", event="ended", terminal="success")),
        event_frame(AttentionEvent(run_id="acme", event="blocked")),
        event_frame(AttentionEvent(run_id="acme", event="ended", node="build", terminal="failed")),
    ]
    with frame_server(frames) as url:
        monkeypatch.setenv("GROOM_URL", url)
        cli.main(["wait", "--run", "acme", "--until", "ended", "--json"])
    captured = capsys.readouterr()
    event = json.loads(captured.out)
    assert event["run_id"] == "acme"
    assert event["terminal"] == "failed"
    assert event["event"] == "ended"
    assert captured.err == ""


@pytest.mark.parametrize("frames", [[], [{"type": "state"}], [{"type": "event", "seq": 1, "ts": 1.0, "event": "invalid"}]])
def test_disconnect_or_incompatible_server_is_monitor_failure(
    frames: list[dict], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    with frame_server(frames) as url:
        monkeypatch.setenv("GROOM_URL", url)
        with pytest.raises(SystemExit) as exit_info:
            cli.main(["wait", "--run", "acme", "--json"])
    assert exit_info.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "monitoring failed" in captured.err


@pytest.mark.parametrize("events", ["", "ended,", "made-up"])
def test_invalid_event_filter_is_usage_error(events: str) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["wait", "--run", "acme", "--until", events])
    assert exit_info.value.code == 2


def test_websocket_route_sends_existing_conditions() -> None:
    state.RUNS["acme"] = RunTelemetry(run_id="acme", terminal="success")
    with TestClient(Litestar(route_handlers=[groom_app.dashboard_ws])) as client:
        with client.websocket_connect("/ws") as socket:
            frame = socket.receive_json()
    assert frame["attention"][0]["run_id"] == "acme"
    assert frame["attention"][0]["event"] == "ended"


def test_alert_dispatch_wakes_cli_before_external_notification(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    async def produce() -> tuple[float, AttentionEvent]:
        queue: asyncio.Queue = asyncio.Queue()
        state.add_feed(queue, "acme")
        state.RUNS["acme"] = RunTelemetry(run_id="acme", current_node="review",
                                          wait_gate_question="Proceed?")

        def push(title: str, message: str) -> None:
            assert not queue.empty(), "the waiter must wake before external push"

        monkeypatch.setattr(groom_app.notify, "push", push)
        try:
            await groom_app._dispatch_alerts([Alert("acme", "BLOCKED", "operator needed")])
            return await queue.get()
        finally:
            state.remove_feed(queue)

    ts, event = asyncio.run(produce())
    assert event.node == "review"
    with frame_server([digest_frame(), EventFrame(seq=2, ts=ts, event=event).model_dump()]) as url:
        monkeypatch.setenv("GROOM_URL", url)
        cli.main(["wait", "--run", "acme", "--json"])
    assert json.loads(capsys.readouterr().out)["question"] == "Proceed?"
