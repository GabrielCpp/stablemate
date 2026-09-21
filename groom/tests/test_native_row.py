"""Native (non-container) runs as first-class dashboard rows."""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from pathlib import Path

from groom import alerts, app as groom_app, gates, localfs, state, store
from groom.models import GateInfo, WorkflowState


def _reset() -> None:
    state.WORKFLOWS.clear()
    state.RUNS.clear()
    state._gate_locks.clear()


def _metric(run_id, name, value, *, run_dir="", workspace="", pid=None, node="", **attrs):
    a = {"node": node} if node else {}
    a.update(attrs)
    return {
        "run_id": run_id, "workflow": "coder", "repo": "acme", "branch": "main",
        "run_dir": run_dir, "workspace": workspace, "pid": pid,
        "name": name, "ts": 1.0, "value": float(value), "attrs": a,
    }


def test_native_run_becomes_a_row(tmp_path):
    _reset()
    run_dir = tmp_path / "coder-run"
    run_dir.mkdir()
    alerts.ingest_metrics([
        _metric("R1", "workhorse.node.active", 1, run_dir=str(run_dir),
                workspace=str(tmp_path), pid=os.getpid(), node="plan",
                **{"activity": "planning ACME-1"}),
    ])
    run = state.RUNS["R1"]
    assert groom_app._sync_native_row(run) is True
    wf = state.WORKFLOWS["R1"]
    assert wf.native is True
    assert wf.state == WorkflowState.RUNNING
    assert wf.current_node == "plan"
    assert wf.activity == "planning ACME-1"
    assert wf.pid == os.getpid()
    assert wf.workspace_volume == str(tmp_path)


def test_wait_kind_alone_blocks_even_without_a_gate_path(tmp_path):
    _reset()
    run_dir = tmp_path / "coder-run"
    run_dir.mkdir()
    alerts.ingest_metrics([
        _metric("R1", "workhorse.wait.active", 1, run_dir=str(run_dir),
                workspace=str(tmp_path), **{"wait_kind": "operator"}),
    ])
    run = state.RUNS["R1"]
    assert groom_app._sync_native_row(run) is True
    wf = state.WORKFLOWS["R1"]
    assert wf.state == WorkflowState.BLOCKED
    assert list(wf.gates.values()) == [GateInfo(workflow_id="R1", file_path="", question="",
                                                 kind="operator")]


def test_containerized_run_is_not_materialized():
    _reset()
    alerts.ingest_metrics([
        _metric("C1", "workhorse.run.heartbeat", 1,
                run_dir="/nonexistent-groom-test/runs/coder-x",
                workspace="/nonexistent-groom-test/workspace", node="impl"),
    ])
    run = state.RUNS["C1"]
    assert groom_app._sync_native_row(run) is False
    assert run.native is False
    assert "C1" not in state.WORKFLOWS


def test_terminal_span_finishes_and_clears_gates(tmp_path):
    _reset()
    run_dir = tmp_path / "r"
    run_dir.mkdir()
    alerts.ingest_metrics([_metric("R2", "workhorse.node.active", 1,
                                   run_dir=str(run_dir), node="qa")])
    groom_app._sync_native_row(state.RUNS["R2"])
    state.WORKFLOWS["R2"].gates["g"] = GateInfo(workflow_id="R2", file_path="g")
    alerts.ingest_spans([{
        "run_id": "R2", "name": "run:coder", "workflow": "coder",
        "attrs": {"workhorse.terminal": "terminal"},
    }])
    groom_app._sync_native_row(state.RUNS["R2"])
    wf = state.WORKFLOWS["R2"]
    assert wf.state == WorkflowState.FINISHED
    assert wf.gates == {}


def test_resumed_run_under_the_same_run_id_goes_back_to_running(tmp_path):
    """``--resume-run`` reuses the run_id (it comes from the run dir), so the previous session's root span arrives under the same key as the new session's telemetry."""
    _reset()
    run_dir = tmp_path / "author-rerun1"
    run_dir.mkdir()
    alerts.ingest_spans([{
        "run_id": "rerun1", "name": "run:author", "workflow": "author",
        "run_dir": str(run_dir), "end_ts": 100.0,
        "attrs": {"workhorse.terminal": "interrupted"},
    }])
    groom_app._sync_native_row(state.RUNS["rerun1"])
    assert state.WORKFLOWS["rerun1"].state == WorkflowState.FINISHED

    beat = _metric("rerun1", "workhorse.run.heartbeat", 1,
                   run_dir=str(run_dir), node="write_story")
    beat["ts"] = 200.0
    alerts.ingest_metrics([beat])
    run = state.RUNS["rerun1"]
    assert run.terminal == ""
    groom_app._sync_native_row(run)
    assert state.WORKFLOWS["rerun1"].state == WorkflowState.RUNNING


def test_a_run_that_goes_silent_still_reads_as_running(tmp_path):
    """The new contract: the row reflects telemetry — silence is not state."""
    _reset()
    run_dir = tmp_path / "r"
    run_dir.mkdir()
    alerts.ingest_metrics([_metric("R5", "workhorse.run.heartbeat", 1,
                                   run_dir=str(run_dir))])
    groom_app._sync_native_row(state.RUNS["R5"])
    assert state.WORKFLOWS["R5"].state == WorkflowState.RUNNING
    stale = time.time() - 10 * store.LIVE_AFTER_S
    run = state.RUNS["R5"]
    run.last_heartbeat_ts = run.first_seen_ts = run.last_span_ts = stale
    groom_app._sync_native_row(run)
    assert state.WORKFLOWS["R5"].state == WorkflowState.RUNNING


def test_disk_terminal_and_dead_pid_do_not_fabricate_telemetry(tmp_path):
    _reset()
    run_dir = tmp_path / "coder-run"
    run_dir.mkdir()
    (run_dir / "run.json").write_text(json.dumps({"terminal": "fail"}))
    dead = subprocess.Popen(["true"])
    dead.wait()
    alerts.ingest_metrics([_metric(
        "reported", "workhorse.run.heartbeat", 1,
        run_dir=str(run_dir), pid=dead.pid,
    )])
    run = state.RUNS["reported"]
    fired: list[alerts.Alert] = []
    groom_app._sync_native_row(run, fired)
    assert run.terminal == ""
    assert state.WORKFLOWS["reported"].state == WorkflowState.RUNNING
    assert fired == []


def test_native_rows_survive_the_docker_prune(tmp_path):
    _reset()
    run_dir = tmp_path / "r"
    run_dir.mkdir()
    alerts.ingest_metrics([_metric("R3", "workhorse.run.heartbeat", 1,
                                   run_dir=str(run_dir))])
    groom_app._sync_native_row(state.RUNS["R3"])
    removed = state.prune_workflows(present_ids=set())
    assert removed == []
    assert "R3" in state.WORKFLOWS


def _git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True)
    (path / "a.txt").write_text("one\n")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=path, check=True)


def test_localfs_lists_files_and_prunes_vendor(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "junk.py").write_text("x")
    files = localfs.list_files(str(tmp_path))
    assert "src/app.py" in files
    assert not any(f.startswith(".venv/") for f in files)


def test_localfs_git_diff(tmp_path):
    _git_repo(tmp_path)
    (tmp_path / "a.txt").write_text("one\ntwo\n")
    diff = localfs.git_diff(str(tmp_path))
    assert "+two" in diff


def test_localfs_read_write_roundtrip_and_traversal_guard(tmp_path):
    assert localfs.write_file(str(tmp_path), "sub/f.md", "hello") is True
    assert localfs.read_file(str(tmp_path), "sub/f.md") == "hello"
    assert localfs.write_file(str(tmp_path), "../escape", "x") is False
    assert localfs.read_file(str(tmp_path), "../escape") is None


def _checkpoint(run_dir: Path, rel: str, state_name: str, waiting_on: str | None) -> None:
    target = run_dir / rel if rel else run_dir
    target.mkdir(parents=True, exist_ok=True)
    (target / "checkpoint.json").write_text(
        json.dumps(
            {
                "engine": "pyflow",
                "state": state_name,
                "waiting_on": waiting_on,
            }
        )
    )


def test_answer_gate_native_writes_local_file(tmp_path):
    _reset()
    gate = tmp_path / "docs" / "gate.md"
    gate.parent.mkdir(parents=True)
    gate.write_text("STATUS: AWAITING_OPERATOR\n\n## Questions from the agent\nProceed?\n")
    result = asyncio.run(gates.answer_gate(
        "R9", "docs/gate.md", "yes, proceed",
        workspace_volume=str(tmp_path), native=True,
    ))
    assert result.ok is True
    written = gate.read_text()
    assert "STATUS: ANSWERED" in written
    assert "yes, proceed" in written


def test_a_zombie_pid_is_not_a_live_run():
    """A killed process keeps its pid until its parent reaps it, and answers signal 0 the whole time."""
    child = subprocess.Popen(["true"])
    try:
        deadline = time.time() + 5
        while time.time() < deadline:
            stat = Path(f"/proc/{child.pid}/stat").read_text()
            if stat.rpartition(")")[2].split()[0] == "Z":
                break
            time.sleep(0.01)
        else:
            raise AssertionError("child never became a zombie")
        assert os.kill(child.pid, 0) is None
        assert localfs.pid_alive(child.pid) is False
    finally:
        child.wait()
