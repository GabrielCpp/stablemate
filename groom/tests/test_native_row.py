"""Native (non-container) runs as first-class dashboard rows.

A native ``workhorse run`` shares groom's host and speaks only telemetry, so:
- its dir existing on this host is the signal that it is native (and the capability
  the local-FS panels rely on) — a containerized run whose paths don't resolve here
  is never materialized as a row and never double-lists;
- the row's "what is it doing" comes from the ``wf.activity`` label carried on the
  live gauges;
- Files/Diff/gate reads go through :mod:`groom.localfs`, not docker.

Run: uv run pytest tests/test_native_row.py
"""
from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from groom import alerts, app as groom_app, gates, localfs, state
from groom.models import WorkflowState


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


# --------------------------------------------------------------------------- #
# Native verdict + row materialization
# --------------------------------------------------------------------------- #
def test_native_run_becomes_a_row(tmp_path):
    _reset()
    run_dir = tmp_path / "coder-run"
    run_dir.mkdir()
    alerts.ingest_metrics([
        _metric("R1", "workhorse.node.active", 1, run_dir=str(run_dir),
                workspace=str(tmp_path), pid=4242, node="plan",
                **{"wf.activity": "planning PRED-1"}),
    ])
    run = state.RUNS["R1"]
    assert groom_app._sync_native_row(run) is True
    wf = state.WORKFLOWS["R1"]
    assert wf.native is True
    assert wf.state == WorkflowState.RUNNING
    assert wf.current_node == "plan"
    assert wf.activity == "planning PRED-1"
    assert wf.pid == 4242
    assert wf.workspace_volume == str(tmp_path)


def test_containerized_run_is_not_materialized():
    _reset()
    # run_dir/workspace are container paths that don't exist on this host.
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
    state.WORKFLOWS["R2"].gates["g"] = object()  # a stand-in open gate
    # The root span arriving with a terminal retires the run.
    alerts.ingest_spans([{
        "run_id": "R2", "name": "run:coder", "workflow": "coder",
        "attrs": {"workhorse.terminal": "terminal"},
    }])
    groom_app._sync_native_row(state.RUNS["R2"])
    wf = state.WORKFLOWS["R2"]
    assert wf.state == WorkflowState.FINISHED
    assert wf.gates == {}


def test_native_rows_survive_the_docker_prune(tmp_path):
    _reset()
    run_dir = tmp_path / "r"
    run_dir.mkdir()
    alerts.ingest_metrics([_metric("R3", "workhorse.run.heartbeat", 1,
                                   run_dir=str(run_dir))])
    groom_app._sync_native_row(state.RUNS["R3"])
    # A docker reconcile that sees no containers must not drop the native row.
    removed = state.prune_workflows(present_ids=set())
    assert removed == []
    assert "R3" in state.WORKFLOWS


# --------------------------------------------------------------------------- #
# local-FS panels
# --------------------------------------------------------------------------- #
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
    # Traversal is rejected, not written outside the base.
    assert localfs.write_file(str(tmp_path), "../escape", "x") is False
    assert localfs.read_file(str(tmp_path), "../escape") is None


# --------------------------------------------------------------------------- #
# Gate answering over local FS
# --------------------------------------------------------------------------- #
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


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
