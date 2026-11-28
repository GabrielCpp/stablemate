"""A push that carries a run id and no container id is keyed by the run."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from test_app import _hermetic_client, _reset
from test_run_keyed_rows import _native_run

from groom import app as groom_app
from groom import live, state, store
from groom import native as groom_native
from groom.models import WorkflowState


@pytest.fixture(autouse=True)
def isolated_store(monkeypatch, tmp_path):
    monkeypatch.setenv("GROOM_DB", str(tmp_path / "groom.db"))
    monkeypatch.setenv("GROOM_FLUSH_S", "0.01")
    store.reset()
    live.reset()
    yield
    live.reset()
    store.reset()


def _post_push(path: str, body: dict) -> dict:
    client = _hermetic_client()
    try:
        return client.post(path, json=body).json()
    finally:
        client.__exit__(None, None, None)


def _refuse_docker():
    def refuse(*_args, **_kwargs):
        raise AssertionError("docker was called for a push with no container")

    return patch.multiple(groom_app.docker_io, docker_inspect=refuse, is_running=refuse, docker_start=refuse)


def test_a_progress_push_with_only_a_run_id_keys_its_row_by_the_run():
    _reset()
    with _refuse_docker():
        reply = _post_push("/push/progress", {"container_id": "", "run_id": "run-push-1", "name": "acme", "current_node": "build"})
    assert reply == {"ok": True}
    wf = state.WORKFLOWS["run-push-1"]
    assert (wf.run_id, wf.containerless, wf.current_node, wf.state) == ("run-push-1", True, "build", WorkflowState.RUNNING)


def test_a_blocked_push_with_only_a_run_id_keys_its_row_by_the_run():
    _reset()
    with _refuse_docker():
        reply = _post_push("/push/blocked", {"run_id": "run-push-2", "file_path": "docs/gate.md", "question": "Which?"})
    assert reply == {"ok": True}
    wf = state.WORKFLOWS["run-push-2"]
    assert wf.state == WorkflowState.BLOCKED
    assert "docs/gate.md" in wf.gates


def test_an_exited_push_with_only_a_run_id_finishes_the_row_of_the_run():
    _reset()
    with _refuse_docker():
        reply = _post_push("/push/exited", {"run_id": "run-push-3", "exit_code": 0})
    assert reply == {"ok": True}
    wf = state.WORKFLOWS["run-push-3"]
    assert (wf.state, wf.exit_code) == (WorkflowState.FINISHED, 0)


def test_a_push_with_neither_key_is_refused():
    _reset()
    assert _post_push("/push/progress", {"current_node": "x"}) == {"ok": False}
    assert _post_push("/push/exited", {"exit_code": 0}) == {"ok": False}
    assert _post_push("/push/blocked", {"file_path": "a.md"}) == {"ok": False}
    assert state.WORKFLOWS == {}


def test_a_push_for_a_native_run_keeps_the_identity_its_telemetry_gave():
    _reset()
    state.RUNS["run-nat"] = _native_run("run-nat")
    groom_native._sync_native_row(state.RUNS["run-nat"])
    _post_push("/push/progress", {"run_id": "run-nat", "name": "acme-box", "repo_name": "other", "current_node": "later"})
    wf = state.WORKFLOWS["run-nat"]
    assert (wf.name, wf.repo_name, wf.current_node, wf.native) == ("coder", "acme", "later", True)
    assert list(state.WORKFLOWS) == ["run-nat"]
