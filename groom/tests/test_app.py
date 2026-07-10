"""App-level tests for the new liveness handlers: the /push/exited endpoint,
the deletion half of /refresh (prune), and the answered-gate state flip +
groom:answered broadcast in _handle_command. Docker and the answer write are
mocked so nothing shells out.

Run: uv run pytest tests/test_app.py
"""
from __future__ import annotations

import asyncio
import contextlib
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


# ---- Files/Diff panels: container+repo picker and per-checkout reads ----
def test_repos_endpoint_lists_one_entry_per_container_repo():
    _reset()
    state.WORKFLOWS["abc123"] = WorkflowContainer(
        container_id="abc123", name="coder-001", workspace_volume="ws-vol", state=WorkflowState.RUNNING
    )
    state.WORKFLOWS["novol"] = WorkflowContainer(container_id="novol", name="pending")  # no volume → skipped

    client = _hermetic_client()
    try:
        with patch.object(groom_app.docker_io, "list_repo_dirs", return_value=["predykt", "yenta"]):
            resp = client.get("/repos")
    finally:
        client.__exit__(None, None, None)

    body = resp.text
    assert body.count('role="option"') == 2
    assert 'data-label="coder-001/predykt"' in body and 'data-label="coder-001/yenta"' in body
    assert "pending" not in body  # volume-less workflow contributes no entry


def test_files_endpoint_returns_newline_separated_paths():
    _reset()
    state.WORKFLOWS["abc123"] = WorkflowContainer(container_id="abc123", name="w", workspace_volume="ws-vol")

    client = _hermetic_client()
    try:
        with patch.object(groom_app.docker_io, "list_files", return_value=["README.md", "src/a.py"]) as lf:
            resp = client.get("/files/abc123", params={"repo": "predykt"})
    finally:
        client.__exit__(None, None, None)

    assert resp.text == "README.md\nsrc/a.py"
    assert lf.call_args[0] == ("ws-vol", "predykt")


def test_file_endpoint_joins_repo_and_path_and_returns_content():
    _reset()
    state.WORKFLOWS["abc123"] = WorkflowContainer(container_id="abc123", name="w", workspace_volume="ws-vol")

    client = _hermetic_client()
    try:
        with patch.object(groom_app.docker_io, "read_file", return_value="print(1)\n") as rf:
            resp = client.get("/file/abc123", params={"repo": "predykt", "path": "src/a.py"})
    finally:
        client.__exit__(None, None, None)

    assert resp.text == "print(1)\n"
    assert rf.call_args[0] == ("ws-vol", "predykt/src/a.py")


def test_file_endpoint_swallows_unsafe_path():
    _reset()
    state.WORKFLOWS["abc123"] = WorkflowContainer(container_id="abc123", name="w", workspace_volume="ws-vol")

    client = _hermetic_client()
    try:
        # read_file raises ValueError on a traversal path; the handler must not 500.
        with patch.object(groom_app.docker_io, "read_file", side_effect=ValueError("unsafe")):
            resp = client.get("/file/abc123", params={"repo": "predykt", "path": "../../etc/passwd"})
    finally:
        client.__exit__(None, None, None)

    assert resp.status_code == 200
    assert resp.text == ""


def test_diff_endpoint_passes_repo_through():
    _reset()
    state.WORKFLOWS["abc123"] = WorkflowContainer(container_id="abc123", name="w", workspace_volume="ws-vol")

    client = _hermetic_client()
    try:
        with patch.object(groom_app.docker_io, "git_diff", return_value="diff --git a/x b/x\n") as gd:
            resp = client.get("/diff/abc123", params={"repo": "predykt"})
    finally:
        client.__exit__(None, None, None)

    assert resp.text == "diff --git a/x b/x\n"
    assert gd.call_args[0] == ("ws-vol", "predykt")


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


# ---- startup only *schedules* discovery; it must not block on the scan ----
def test_spawn_scan_returns_before_discovery_completes():
    _reset()
    order: list[str] = []

    async def _slow_reconcile() -> int:
        order.append("scan-start")
        await asyncio.sleep(0.02)
        order.append("scan-done")
        return 0

    async def _scenario() -> None:
        with patch.object(groom_app, "_reconcile", _slow_reconcile):
            await groom_app._spawn_scan()
            order.append("spawn-returned")
            await groom_app._scan_task  # let the background task finish

    asyncio.run(_scenario())

    # spawn returned before the scan even started running — i.e. non-blocking.
    assert order[0] == "spawn-returned"
    assert "scan-done" in order
    assert state.SCANNING is False


# ---- SCANNING is cleared even if the background scan raises ----
def test_background_scan_clears_scanning_on_error():
    _reset()
    state.SCANNING = True

    async def _boom() -> int:
        raise RuntimeError("docker exploded")

    async def _scenario() -> None:
        with patch.object(groom_app, "_reconcile", _boom):
            with contextlib.suppress(RuntimeError):
                await groom_app._background_scan()

    asyncio.run(_scenario())
    assert state.SCANNING is False


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
