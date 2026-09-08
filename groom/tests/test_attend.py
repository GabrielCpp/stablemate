"""The attendant: who gets dispatched at a run that parked or died, and who does not.

A fake clock and a fake spawner throughout — no agent process, no socket, no run.
What is under test is the decision, which is the whole of :mod:`groom.attend`: the
dispatch itself is one `Popen` behind a port.

Run: uv run pytest groom/tests/test_attend.py
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from litestar.testing import TestClient

from groom import app as groom_app
from groom import attend, discovery, state
from groom.models import GateInfo, WorkflowContainer, WorkflowState


class _Spawner:
    """The dispatch port, recording instead of spawning."""

    def __init__(self) -> None:
        self.jobs: list[attend.AttendJob] = []

    def __call__(self, job: attend.AttendJob) -> None:
        self.jobs.append(job)


def _headless(monkeypatch) -> _Spawner:
    monkeypatch.setenv("GROOM_ATTEND", "headless")
    attend.reset()
    return _Spawner()


def _gate(
    *, question: str = "What now?", gate_path: str = "docs/gate.md",
    kind: str = "operator", now: float = 0.0, spawner=None,
) -> attend.AttendJob | None:
    """One parked run, with only the fields any of these cases vary."""
    return attend.attend_gate(
        run_id="r1", workflow="okf-builder", run_dir="/runs/r1", workspace="/repo",
        gate_path=gate_path, question=question, kind=kind, now=now, spawner=spawner,
    )


def test_attending_is_off_until_it_is_configured(monkeypatch):
    """The default is the dashboard groom already was — not a degraded attendant."""
    monkeypatch.delenv("GROOM_ATTEND", raising=False)
    attend.reset()
    spawner = _Spawner()
    assert _gate(spawner=spawner, now=0.0) is None
    assert spawner.jobs == []
    assert attend.queue() == []


def test_one_fresh_gate_dispatches_once_and_a_second_announcement_does_not(monkeypatch):
    """The same still-open gate re-announced is the same stop, not a second one."""
    spawner = _headless(monkeypatch)
    assert _gate(spawner=spawner, now=0.0) is not None
    assert _gate(spawner=spawner, now=1.0) is None
    assert len(spawner.jobs) == 1
    assert [job["kind"] for job in attend.queue()] == ["gate"]


def test_a_gate_re_armed_after_an_answer_is_a_new_stop(monkeypatch):
    """`release` is the run coming back; the next park is a park nobody has seen."""
    spawner = _headless(monkeypatch)
    _gate(spawner=spawner, now=0.0)
    attend.release("r1")
    assert attend.queue() == []
    assert _gate(spawner=spawner, now=10.0) is not None
    assert len(spawner.jobs) == 2


def test_a_machine_wait_is_never_attended(monkeypatch):
    """A 40-hour measurement is not a human failing to answer a gate."""
    spawner = _headless(monkeypatch)
    assert _gate(spawner=spawner, now=0.0, kind="machine") is None
    assert spawner.jobs == []


def test_a_deny_listed_gate_is_never_attended(monkeypatch):
    """Some gates are an infrastructure wall, not a question answered by trying harder."""
    spawner = _headless(monkeypatch)
    monkeypatch.setenv("GROOM_ATTEND_DENY", "push the pr,credential")
    assert _gate(spawner=spawner, now=0.0, question="Could not PUSH THE PR") is None
    assert _gate(spawner=spawner, now=0.0, gate_path="docs/credential-wall.md") is None
    assert spawner.jobs == []


def test_the_budget_stops_the_nth_attempt_inside_the_window(monkeypatch):
    """A gate the attendant cannot clear must not spin an unbounded run of turns."""
    spawner = _headless(monkeypatch)
    monkeypatch.setenv("GROOM_ATTEND_MAX", "2")
    monkeypatch.setenv("GROOM_ATTEND_WINDOW_MIN", "10")
    for at in (0.0, 1.0, 2.0):
        _gate(spawner=spawner, now=at)
        attend.release("r1")
    assert len(spawner.jobs) == 2
    # Past the window the budget refills — the bound is a rate, not a lifetime cap.
    _gate(spawner=spawner, now=1000.0)
    assert len(spawner.jobs) == 3


def test_session_mode_publishes_the_job_and_spawns_nothing(monkeypatch):
    """The whole point of `session`: an interactive Claude claims it from the queue."""
    monkeypatch.setenv("GROOM_ATTEND", "session")
    attend.reset()
    spawner = _Spawner()
    job = _gate(spawner=spawner, now=0.0)
    assert job is not None
    assert spawner.jobs == []
    assert [entry["gate_path"] for entry in attend.queue()] == ["docs/gate.md"]


def test_a_spawn_that_raises_leaves_the_job_published(monkeypatch):
    """The watch on a stopped run must not itself be able to stop."""
    _headless(monkeypatch)

    def _explode(job: attend.AttendJob) -> None:
        raise OSError("no claude here")

    assert _gate(spawner=_explode, now=0.0) is not None
    assert len(attend.queue()) == 1


# ---- the dead half -------------------------------------------------------------
def _failure_run(tmp_path: Path) -> str:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "inbox.jsonl").write_text(
        json.dumps({
            "id": "1", "at": "2026-09-08T00:00:00Z", "kind": "failure",
            "body": "failure_class: AgentTurnFailed\nnode: adjudicate\nerror: boom",
        }) + "\n"
    )
    return str(run_dir)


def test_a_dead_run_is_routed_by_the_class_it_recorded(monkeypatch, tmp_path):
    """This half has the machine-readable class the gates lack — read it, don't parse prose."""
    spawner = _headless(monkeypatch)
    job = attend.attend_death(
        run_id="r1", workflow="okf-builder", run_dir=_failure_run(tmp_path),
        workspace="/repo", now=0.0, spawner=spawner,
    )
    assert job is not None
    assert (job.failure_class, job.node) == ("AgentTurnFailed", "adjudicate")
    assert "boom" in job.prompt()


def test_a_run_that_left_no_handoff_is_still_attended(monkeypatch, tmp_path):
    """A SIGKILL writes nothing; the empty class is what sends it to the checkpoint."""
    spawner = _headless(monkeypatch)
    job = attend.attend_death(
        run_id="r1", workflow="okf-builder", run_dir=str(tmp_path), workspace="/repo",
        now=0.0, spawner=spawner,
    )
    assert job is not None and job.failure_class == ""
    assert "checkpoint.json" in job.prompt()


def test_a_job_carries_the_gate_body_verbatim(monkeypatch):
    """Three incompatible gate formats are in the tree; handing the text over intact
    is the only thing that covers all of them."""
    spawner = _headless(monkeypatch)
    body = "## Blocked\n\n- tried: reload\n- tried: answer\n"
    job = _gate(spawner=spawner, now=0.0, question=body)
    assert job is not None and body in job.prompt()


# ---- the app edges -------------------------------------------------------------
def _reset_fleet() -> None:
    state.WORKFLOWS.clear()
    state.RUNS.clear()
    state.SCANNING = False
    attend.reset()


def _client() -> TestClient:
    with patch.object(discovery, "scan", return_value=[]), \
         patch.object(discovery, "present_container_ids", return_value=None):
        client = TestClient(app=groom_app.create_app())
        client.__enter__()
    return client


def _native_row(exit_code: int | None = None) -> WorkflowContainer:
    return WorkflowContainer(
        container_id="r1", name="okf-builder", native=True, workflow_type="okf-builder",
        workspace_volume="/repo", runs_volume="/runs/r1", state=WorkflowState.RUNNING,
        exit_code=exit_code,
    )


def test_an_exit_that_is_a_death_dispatches_and_a_reload_does_not(monkeypatch, tmp_path):
    """Exit 3 is the supervisor restarting the run on purpose — not something to attend."""
    monkeypatch.setenv("GROOM_ATTEND", "session")
    client = _client()
    try:
        for code, expected in ((3, 0), (0, 0), (1, 1)):
            _reset_fleet()
            row = _native_row()
            row.runs_volume = str(tmp_path)
            state.WORKFLOWS["r1"] = row
            client.post("/push/exited", json={"container_id": "r1", "exit_code": code})
            assert len(attend.queue()) == expected, code
    finally:
        client.__exit__(None, None, None)


def test_the_queue_endpoint_lists_the_fleet(monkeypatch):
    """One endpoint for every outstanding job, rather than one watch loop per run id."""
    monkeypatch.setenv("GROOM_ATTEND", "session")
    _reset_fleet()
    _gate(now=0.0)
    attend.attend_gate(
        run_id="r2", workflow="coder", run_dir="/runs/r2", workspace="/repo2",
        gate_path="docs/other.md", question="And this?", now=1.0,
    )
    client = _client()
    try:
        payload = client.get("/api/attend/queue").json()
    finally:
        client.__exit__(None, None, None)
    assert payload["mode"] == "session"
    assert [job["run_id"] for job in payload["jobs"]] == ["r1", "r2"]


def test_a_container_row_is_not_attended_from_this_host(monkeypatch):
    """Its `runs_volume` is a docker volume name — an attendant here has nothing to open."""
    monkeypatch.setenv("GROOM_ATTEND", "session")
    _reset_fleet()
    row = _native_row()
    row.native = False
    row.gates["docs/gate.md"] = GateInfo(workflow_id="r1", file_path="docs/gate.md")
    state.WORKFLOWS["r1"] = row
    groom_app._attend_gates(row, list(row.gates.values()))
    assert attend.queue() == []


def test_gates_clearing_releases_the_run(monkeypatch):
    """A row with no gates is a run that is going again, whoever cleared it."""
    monkeypatch.setenv("GROOM_ATTEND", "session")
    _reset_fleet()
    row = _native_row()
    gate = GateInfo(workflow_id="r1", file_path="docs/gate.md", question="Q?", kind="operator")
    row.gates[gate.file_path] = gate
    state.WORKFLOWS["r1"] = row
    groom_app._attend_gates(row, [gate])
    assert len(attend.queue()) == 1
    row.gates.clear()
    groom_app._attend_gates(row, [])
    assert attend.queue() == []
