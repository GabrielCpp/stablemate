"""Native (non-container) runs as first-class dashboard rows.

A native run shares groom's host and speaks only telemetry, so:
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
import json
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
                **{"activity": "planning PRED-1"}),
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
    state.WORKFLOWS["R2"].gates["g"] = GateInfo(workflow_id="R2", file_path="g")
    # …an open gate, which the terminal span below has to clear.
    # The root span arriving with a terminal retires the run.
    alerts.ingest_spans([{
        "run_id": "R2", "name": "run:coder", "workflow": "coder",
        "attrs": {"workhorse.terminal": "terminal"},
    }])
    groom_app._sync_native_row(state.RUNS["R2"])
    wf = state.WORKFLOWS["R2"]
    assert wf.state == WorkflowState.FINISHED
    assert wf.gates == {}


def test_resumed_run_under_the_same_run_id_goes_back_to_running(tmp_path):
    """``--resume-run`` reuses the run_id (it comes from the run dir), so the
    previous session's root span arrives under the same key as the new session's
    telemetry. The row must follow the live process, not the dead one."""
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

    # The resumed session beats. One point stamped after that root span is all the
    # evidence there is that a process is alive — and it has to be enough.
    beat = _metric("rerun1", "workhorse.run.heartbeat", 1,
                   run_dir=str(run_dir), node="write_story")
    beat["ts"] = 200.0
    alerts.ingest_metrics([beat])
    run = state.RUNS["rerun1"]
    assert run.terminal == ""
    groom_app._sync_native_row(run)
    assert state.WORKFLOWS["rerun1"].state == WorkflowState.RUNNING


def test_a_run_that_goes_silent_stops_reading_as_running(tmp_path):
    """The other half: nothing arrives to mark a run stopped — silence is an
    absence — so the row's state has to be re-derived from the clock."""
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
    assert state.WORKFLOWS["R5"].state == WorkflowState.FINISHED


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
# Gates raised inside a sub-flow
# --------------------------------------------------------------------------- #
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


def test_native_gate_raised_inside_a_subflow_is_found(tmp_path):
    """The blocking `Await` belongs to the child flow's checkpoint; the root only
    names the node that handed off to it. Reading the root alone left the run
    blocked with nothing on the dashboard to answer."""
    _reset()
    run_dir = tmp_path / "runs" / "coder-r1"
    workspace = tmp_path / "workspace"
    gate = workspace / "docs" / "story" / "context.md"
    gate.parent.mkdir(parents=True)
    gate.write_text("STATUS: AWAITING_OPERATOR\n\n## Questions from the agent\nWhich corpus?\n")
    _checkpoint(run_dir, "", "review", None)
    _checkpoint(run_dir, "review/_flow", "read_operator", str(gate))

    alerts.ingest_metrics(
        [
            _metric(
                "C1", "workhorse.run.heartbeat", 1,
                run_dir=str(run_dir), workspace=str(workspace), node="review",
            )
        ],
        now=time.time(),
    )

    assert groom_app._sync_native_row(state.RUNS["C1"]) is True
    wf = state.WORKFLOWS["C1"]
    assert wf.state == WorkflowState.BLOCKED
    assert wf.gates["docs/story/context.md"].question == "Which corpus?"


def test_native_gate_ignores_a_finished_siblings_checkpoint(tmp_path):
    """A flow node inside a loop leaves its `_flow` scope behind. Only the chain the
    root's current state names is followed, so the previous story's gate — still
    AWAITING because nobody ever answered it — is not re-raised."""
    _reset()
    run_dir = tmp_path / "runs" / "coder-r2"
    workspace = tmp_path / "workspace"
    stale = workspace / "docs" / "old.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("STATUS: AWAITING_OPERATOR\n\n## Questions from the agent\nStale?\n")
    _checkpoint(run_dir, "", "dev", None)
    _checkpoint(run_dir, "dev/_flow", "layer", None)
    _checkpoint(run_dir, "qa/_flow", "resolve_operator", str(stale))

    alerts.ingest_metrics(
        [
            _metric(
                "C2", "workhorse.run.heartbeat", 1,
                run_dir=str(run_dir), workspace=str(workspace), node="dev",
            )
        ],
        now=time.time(),
    )

    groom_app._sync_native_row(state.RUNS["C2"])
    wf = state.WORKFLOWS["C2"]
    assert wf.gates == {}
    assert wf.state == WorkflowState.RUNNING


def test_active_waiting_on_stops_at_the_depth_bound(tmp_path):
    """A checkpoint whose state names its own scope would otherwise walk forever."""
    run_dir = tmp_path / "loop"
    for depth in range(groom_app._MAX_FLOW_DEPTH + 3):
        _checkpoint(run_dir, "/".join(["self/_flow"] * depth), "self", None)
    assert groom_app._active_waiting_on(str(run_dir)) == ""


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


def test_native_pyflow_wait_materializes_and_answers_a_legacy_gate(tmp_path):
    _reset()
    run_dir = tmp_path / "runs" / "author-r1"
    workspace = tmp_path / "workspace"
    gate = workspace / "docs" / "context.md"
    run_dir.mkdir(parents=True)
    gate.parent.mkdir(parents=True)
    gate.write_text("Which interaction policy should the story use?\n")
    (run_dir / "checkpoint.json").write_text(
        "{"
        '"engine":"pyflow","state":"write_story",'
        f'"waiting_on":"{gate}"'
        "}"
    )
    alerts.ingest_metrics(
        [
            _metric(
                "A1",
                "workhorse.run.heartbeat",
                1,
                run_dir=str(run_dir),
                workspace=str(workspace),
                node="write_story",
            )
        ],
        now=time.time(),
    )

    assert groom_app._sync_native_row(state.RUNS["A1"]) is True
    wf = state.WORKFLOWS["A1"]
    assert wf.state == WorkflowState.BLOCKED
    assert wf.gates["docs/context.md"].legacy_headerless is True

    result = asyncio.run(
        gates.answer_gate(
            "A1",
            "docs/context.md",
            "Define it consistently with the epic and mockup.",
            workspace_volume=str(workspace),
            native=True,
            allow_headerless=True,
        )
    )
    assert result.ok is True
    assert gate.read_text().startswith("STATUS: ANSWERED")


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
