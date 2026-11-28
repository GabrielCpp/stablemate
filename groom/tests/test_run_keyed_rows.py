"""A sidecar that sends no container id: the row and the connection are keyed by its run, and no Docker call is made for it."""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from test_app import _hermetic_client, _noop_ensure_volumes, _reset, _sidecar_frames

from groom import app as groom_app
from groom import projection
from groom import discovery, live, sidecar_hub, state, store
from groom import native as groom_native
from groom.models import RunTelemetry, WorkflowContainer


@pytest.fixture(autouse=True)
def isolated_store(monkeypatch, tmp_path):
    monkeypatch.setenv("GROOM_DB", str(tmp_path / "groom.db"))
    monkeypatch.setenv("GROOM_FLUSH_S", "0.01")
    store.reset()
    live.reset()
    yield
    live.reset()
    store.reset()


def _run_hello(run_id: str, *, container_id: str = "", node: str = "build", gates=()) -> dict:
    return {
        "type": "hello",
        "identity": {"container_id": container_id, "name": "acme", "run_id": run_id, "workflow": "coder"},
        "snapshot": {"current_node": node, "terminal": "", "gates": list(gates)},
    }


def _next_run_frame(tab, run_id: str, *, sidecar: bool | None = None):
    for frame in _sidecar_frames(tab):
        if frame["run"]["id"] == run_id and (sidecar is None or frame["run"]["sidecar"] is sidecar):
            return frame
    raise AssertionError(f"no run frame for {run_id}")


def test_a_sidecar_with_no_container_registers_by_its_run():
    _reset()
    client = _hermetic_client()
    try:
        with patch("groom.native._ensure_volumes", _noop_ensure_volumes):
            with client.websocket_connect("/ws") as tab:
                tab.receive_json()
                with client.websocket_connect("/sidecar") as sidecar_socket:
                    sidecar_socket.send_json(_run_hello("run-remote-1"))
                    seen = _next_run_frame(tab, "run-remote-1", sidecar=True)
                    assert seen["run"]["sidecar"] is True
                    assert list(sidecar_hub.CONNECTIONS) == ["run-remote-1"]
                    assert state.WORKFLOWS["run-remote-1"].run_id == "run-remote-1"
                    assert state.WORKFLOWS["run-remote-1"].containerless is True
                while "run-remote-1" in state.WORKFLOWS:
                    tab.receive_json()
                assert sidecar_hub.CONNECTIONS == {}
    finally:
        client.__exit__(None, None, None)


def test_a_hello_with_neither_key_is_not_registered_and_the_next_one_is():
    _reset()
    client = _hermetic_client()
    try:
        with patch("groom.native._ensure_volumes", _noop_ensure_volumes):
            with client.websocket_connect("/ws") as tab:
                tab.receive_json()
                with client.websocket_connect("/sidecar") as sidecar_socket:
                    sidecar_socket.send_json(_run_hello(""))
                    sidecar_socket.send_json(_run_hello("run-late-1"))
                    _next_run_frame(tab, "run-late-1", sidecar=True)
                    assert list(sidecar_hub.CONNECTIONS) == ["run-late-1"]
                    assert list(state.WORKFLOWS) == ["run-late-1"]
    finally:
        client.__exit__(None, None, None)


def test_a_later_hello_that_changes_the_key_drops_the_old_registration_and_row():
    _reset()
    client = _hermetic_client()
    try:
        with patch("groom.native._ensure_volumes", _noop_ensure_volumes):
            with client.websocket_connect("/ws") as tab:
                tab.receive_json()
                with client.websocket_connect("/sidecar") as sidecar_socket:
                    sidecar_socket.send_json(_run_hello("run-first"))
                    _next_run_frame(tab, "run-first", sidecar=True)
                    sidecar_socket.send_json(_run_hello("run-second"))
                    _next_run_frame(tab, "run-second", sidecar=True)
                    assert list(sidecar_hub.CONNECTIONS) == ["run-second"]
                    assert list(state.WORKFLOWS) == ["run-second"]
    finally:
        client.__exit__(None, None, None)


def test_two_sidecars_on_one_host_with_different_runs_are_two_rows():
    _reset()
    client = _hermetic_client()
    try:
        with patch("groom.native._ensure_volumes", _noop_ensure_volumes):
            with client.websocket_connect("/ws") as tab:
                tab.receive_json()
                with client.websocket_connect("/sidecar") as one, client.websocket_connect("/sidecar") as two:
                    one.send_json(_run_hello("run-a"))
                    _next_run_frame(tab, "run-a", sidecar=True)
                    two.send_json(_run_hello("run-b"))
                    _next_run_frame(tab, "run-b", sidecar=True)
                    assert sorted(state.WORKFLOWS) == ["run-a", "run-b"]
                    assert sorted(sidecar_hub.CONNECTIONS) == ["run-a", "run-b"]
    finally:
        client.__exit__(None, None, None)


def _native_run(run_id: str) -> RunTelemetry:
    return RunTelemetry(run_id=run_id, workflow="coder", repo="acme", branch="main", run_dir="/tmp", workspace="/tmp", native=True, current_node="plan")


def test_a_sidecar_and_the_native_run_are_one_row_that_survives_the_sidecar_dropping():
    _reset()
    state.RUNS["run-both"] = _native_run("run-both")
    groom_native._sync_native_row(state.RUNS["run-both"])
    client = _hermetic_client()
    try:
        with patch("groom.native._ensure_volumes", _noop_ensure_volumes):
            with client.websocket_connect("/ws") as tab:
                tab.receive_json()
                with client.websocket_connect("/sidecar") as sidecar_socket:
                    gate = {"file_path": "docs/gate.md", "question": "Which?"}
                    sidecar_socket.send_json(_run_hello("run-both", node="build", gates=[gate]))
                    seen = _next_run_frame(tab, "run-both", sidecar=True)
                    assert seen["run"]["native"] is True
                    assert list(state.WORKFLOWS) == ["run-both"]
                    wf = state.WORKFLOWS["run-both"]
                    assert wf.native is True
                    assert wf.current_node == "build"
                    assert "docs/gate.md" in wf.gates
                    groom_native._sync_native_row(state.RUNS["run-both"])
                    assert list(state.WORKFLOWS) == ["run-both"]
                    assert "docs/gate.md" in state.WORKFLOWS["run-both"].gates
                _next_run_frame(tab, "run-both", sidecar=False)
                assert list(state.WORKFLOWS) == ["run-both"]
                assert state.WORKFLOWS["run-both"].native is True
    finally:
        client.__exit__(None, None, None)


def test_a_row_without_a_container_id_never_calls_docker():
    _reset()

    def refuse(*_args, **_kwargs):
        raise AssertionError("docker was called for a row with no container")

    async def _scenario() -> None:
        async def _noop_broadcast(fragment) -> None:
            pass

        with patch.object(groom_app.docker_io, "docker_inspect", refuse), \
             patch.object(groom_app.docker_io, "is_running", refuse), \
             patch.object(groom_app.docker_io, "docker_start", refuse), \
             patch.object(groom_app.docker_io, "sidecar_query", refuse), \
             patch.object(discovery, "scan", return_value=[]), \
             patch.object(discovery, "present_container_ids", return_value=set()), \
             patch.object(state, "broadcast", _noop_broadcast):
            await groom_app._apply_hello("run-nodocker", _run_hello("run-nodocker"))
            await groom_native._reconcile()

    asyncio.run(_scenario())
    assert "run-nodocker" in state.WORKFLOWS


def test_the_row_says_whether_the_run_has_no_container():
    assert projection.run_row(WorkflowContainer(container_id="abc123def456", name="demo"))["containerless"] is False
    assert projection.run_row(WorkflowContainer(container_id="run-x", name="demo", containerless=True))["containerless"] is True
