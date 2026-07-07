"""App-level tests for the new liveness handlers: the /push/exited endpoint,
the deletion half of /refresh (prune), and the answered-gate state flip +
groom:answered broadcast in _handle_command. Docker and the answer write are
mocked so nothing shells out.

Run: uv run pytest tests/test_app.py
"""
from __future__ import annotations

import asyncio
from unittest.mock import patch

from litestar.testing import TestClient

from groom import app as groom_app
from groom import discovery, state
from groom.models import AnswerResult, GateInfo, WorkflowContainer, WorkflowState


def _reset() -> None:
    state.WORKFLOWS.clear()
    state._gate_locks.clear()
    state.CLIENTS.clear()


def _hermetic_client() -> TestClient:
    # Startup runs _startup_scan → keep it off real docker.
    with patch.object(discovery, "scan", return_value=[]), \
         patch.object(discovery, "present_container_ids", return_value=None):
        client = TestClient(app=groom_app.create_app())
        client.__enter__()
    return client


# ---- /push/exited marks the worker FINISHED, records the code, clears gates ----
def test_push_exited_marks_finished_clears_gates_and_records_code():
    _reset()
    wf = WorkflowContainer(container_id="abc123", name="w", state=WorkflowState.BLOCKED, workspace_volume="v")
    wf.gates["docs/gate.md"] = GateInfo(workflow_id="abc123", file_path="docs/gate.md", question="Q?")
    state.WORKFLOWS["abc123"] = wf

    client = _hermetic_client()
    try:
        # already has a volume, so _ensure_volumes is a no-op (no docker call)
        resp = client.post("/push/exited", json={"container_id": "abc123", "exit_code": 2})
    finally:
        client.__exit__(None, None, None)

    assert resp.json() == {"ok": True}
    assert state.WORKFLOWS["abc123"].state == WorkflowState.FINISHED
    assert state.WORKFLOWS["abc123"].exit_code == 2
    assert state.WORKFLOWS["abc123"].gates == {}


def test_push_exited_rejects_missing_container_id():
    _reset()
    client = _hermetic_client()
    try:
        resp = client.post("/push/exited", json={"exit_code": 0})
    finally:
        client.__exit__(None, None, None)
    assert resp.json() == {"ok": False}


# ---- /refresh prunes containers the scan no longer sees ----
def test_refresh_prunes_vanished_containers():
    _reset()
    state.WORKFLOWS["gone"] = WorkflowContainer(container_id="gone", name="gone")

    with patch.object(discovery, "scan", return_value=[]), \
         patch.object(discovery, "present_container_ids", return_value=set()):
        client = TestClient(app=groom_app.create_app())
        with client:
            resp = client.post("/refresh")

    assert resp.json()["ok"] is True
    assert "gone" not in state.WORKFLOWS


def test_refresh_skips_prune_when_docker_unavailable():
    _reset()
    state.WORKFLOWS["keep"] = WorkflowContainer(container_id="keep", name="keep")

    with patch.object(discovery, "scan", return_value=[]), \
         patch.object(discovery, "present_container_ids", return_value=None):
        client = TestClient(app=groom_app.create_app())
        with client:
            client.post("/refresh")

    # None means "can't tell" → fleet retained, not wiped.
    assert "keep" in state.WORKFLOWS


# ---- answered gate: state flips to RUNNING + groom:answered is broadcast ----
def test_handle_answer_flips_state_and_broadcasts_answered_script():
    _reset()
    wf = WorkflowContainer(container_id="abc123", name="w", state=WorkflowState.BLOCKED, workspace_volume="v")
    wf.gates["docs/gate.md"] = GateInfo(workflow_id="abc123", file_path="docs/gate.md", question="Q?")
    state.WORKFLOWS["abc123"] = wf

    captured = {}

    async def _fake_answer_gate(cid, fp, ans, *, workspace_volume):
        state.clear_gate(cid, fp)  # mirror the real clear
        return AnswerResult(ok=True, message="answered")

    async def _capture_broadcast(fragment):
        captured["fragment"] = fragment

    with patch.object(groom_app, "answer_gate", _fake_answer_gate), \
         patch.object(state, "broadcast", _capture_broadcast):
        asyncio.run(
            groom_app._handle_command(
                {"cmd": "answer", "workflow_id": "abc123", "file_path": "docs/gate.md", "answer": "yes"}
            )
        )

    assert state.WORKFLOWS["abc123"].state == WorkflowState.RUNNING
    assert "groom:answered" in captured["fragment"]
    assert "abc123" in captured["fragment"]


def test_handle_answer_failure_does_not_flip_or_dispatch():
    _reset()
    wf = WorkflowContainer(container_id="abc123", name="w", state=WorkflowState.BLOCKED, workspace_volume="v")
    wf.gates["docs/gate.md"] = GateInfo(workflow_id="abc123", file_path="docs/gate.md", question="Q?")
    state.WORKFLOWS["abc123"] = wf

    captured = {}

    async def _fake_answer_gate(cid, fp, ans, *, workspace_volume):
        return AnswerResult(ok=False, message="already answered in another tab")

    async def _capture_broadcast(fragment):
        captured["fragment"] = fragment

    with patch.object(groom_app, "answer_gate", _fake_answer_gate), \
         patch.object(state, "broadcast", _capture_broadcast):
        asyncio.run(
            groom_app._handle_command(
                {"cmd": "answer", "workflow_id": "abc123", "file_path": "docs/gate.md", "answer": "yes"}
            )
        )

    # Gate still open, still blocked, no answered event.
    assert state.WORKFLOWS["abc123"].state == WorkflowState.BLOCKED
    assert "groom:answered" not in captured["fragment"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
