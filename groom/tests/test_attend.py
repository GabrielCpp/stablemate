"""The attendant: who gets dispatched at a run that stopped, and what is recorded.

Three layers, all of them here because they are one feature:

* the **decision** — which stops are attended and which are left alone;
* the **lifecycle** — a row written before the attendant's first byte, flipped by the
  thread that owns the process, restarted in place after a groom that died;
* the **record** — a copied transcript read back as a conversation, and the endpoints
  the pane calls.

No agent process and no socket: the CLI launch is one function behind a port, and
every test that needs a process either fakes it or spawns a sleeper it then kills.

Run: uv run pytest groom/tests/test_attend.py
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from litestar.testing import TestClient

from groom import app as groom_app
from groom import attend, attend_transcript, discovery, gates, state, store
from groom.models import GateInfo, WorkflowContainer, WorkflowState

WAIT_S = 5.0


class _Spawner:
    """The dispatch port, recording instead of spawning."""

    def __init__(self) -> None:
        self.jobs: list[attend.AttendJob] = []

    def __call__(self, job: attend.AttendJob) -> None:
        self.jobs.append(job)


class _FakeProc:
    """A process that ends when the test says so, and never before."""

    def __init__(self, pid: int = 4242, code: int = 0) -> None:
        self.pid = pid
        self.code = code
        self.stdin = None
        self.done = threading.Event()

    def wait(self) -> int:
        self.done.wait(WAIT_S)
        return self.code


Configure = Callable[..., _Spawner]


@pytest.fixture
def attending(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Configure]:
    """A groom whose database, config and transcript root are all this test's own.

    The mode is read from settings on every announcement, so the fixture writes the
    environment tier and drops the settings cache — a test that set an environment
    variable and left a cached resolution behind would be testing the previous case.
    """

    def _configure(mode: str = attend.HEADLESS, **env: str) -> _Spawner:
        monkeypatch.setenv("GROOM_DB", str(tmp_path / "groom.db"))
        monkeypatch.setenv("STABLEMATE_CONFIG", str(tmp_path / "config.toml"))
        monkeypatch.delenv("WORKHORSE_CONFIG", raising=False)
        monkeypatch.delenv("GROOM_ATTEND_DENY", raising=False)
        if mode == attend.OFF:
            monkeypatch.delenv("GROOM_ATTEND", raising=False)
        else:
            monkeypatch.setenv("GROOM_ATTEND", mode)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        store.reset()
        attend.reset()
        attend.forget_settings()
        return _Spawner()

    yield _configure
    store.reset()
    attend.reset()
    attend.forget_settings()


def _gate(
    *, question: str = "What now?", gate_path: str = "docs/gate.md",
    kind: str = "operator", now: float = 0.0, spawner: Any = None,
    run_id: str = "r1",
) -> attend.AttendJob | None:
    """One parked run, with only the fields any of these cases vary."""
    return attend.attend_gate(
        run_id=run_id, workflow="okf-builder", run_dir="/runs/r1", workspace="/repo",
        gate_path=gate_path, question=question, kind=kind, now=now, spawner=spawner,
    )


def _await(predicate: Callable[[], bool], what: str) -> None:
    """Spin until the owning thread has done its work, or say what never happened."""
    deadline = time.monotonic() + WAIT_S
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError(f"timed out waiting for {what}")


# ---- the decision --------------------------------------------------------------
def test_attending_is_off_until_it_is_configured(attending: Configure):
    """The default is the dashboard groom already was — not a degraded attendant."""
    spawner = attending(attend.OFF)
    assert _gate(spawner=spawner) is None
    assert spawner.jobs == []
    assert attend.queue() == []


def test_one_fresh_gate_dispatches_once_and_a_second_announcement_does_not(
    attending: Configure,
):
    """The same still-open gate re-announced is the same stop, not a second one."""
    spawner = attending()
    assert _gate(spawner=spawner, now=0.0) is not None
    assert _gate(spawner=spawner, now=1.0) is None
    assert len(spawner.jobs) == 1
    assert [job["kind"] for job in attend.queue()] == ["gate"]


def test_a_gate_re_armed_after_an_answer_is_a_new_stop(attending: Configure):
    """`release` is the run coming back; the next park is a park nobody has seen."""
    spawner = attending()
    _gate(spawner=spawner, now=0.0)
    attend.release("r1")
    assert attend.queue() == []
    assert _gate(spawner=spawner, now=10.0) is not None
    assert len(spawner.jobs) == 2


def test_a_running_row_holds_the_run_after_the_ledger_is_gone(attending: Configure):
    """The durable half of "one attendant per run": groom restarted, the claude did not.

    Nothing is in memory after a restart, so a run that is still parked would collect a
    second attendant on the first tick if the ``running`` row did not answer for it.
    """
    spawner = attending()
    assert _gate(spawner=spawner) is not None
    store.attend_start("job-1", run_id="r1", kind="gate", started_at=0.0)
    attend.reset()
    assert _gate(spawner=spawner) is None
    store.attend_finish("job-1", exit_code=0)
    assert _gate(spawner=spawner) is not None


def test_a_machine_wait_is_never_attended(attending: Configure):
    """A 40-hour measurement is not a human failing to answer a gate."""
    spawner = attending()
    assert _gate(spawner=spawner, kind="machine") is None
    assert spawner.jobs == []


def test_a_deny_listed_gate_is_never_attended(attending: Configure):
    """Some gates are an infrastructure wall, not a question answered by trying harder."""
    spawner = attending(GROOM_ATTEND_DENY="push the pr,credential")
    assert _gate(spawner=spawner, question="Could not PUSH THE PR") is None
    assert _gate(spawner=spawner, gate_path="docs/credential-wall.md") is None
    assert spawner.jobs == []


def test_session_mode_publishes_the_job_and_spawns_nothing(attending: Configure):
    """The whole point of `session`: an interactive Claude claims it from the queue."""
    spawner = attending(attend.SESSION)
    assert _gate(spawner=spawner) is not None
    assert spawner.jobs == []
    assert [entry["gate_path"] for entry in attend.queue()] == ["docs/gate.md"]
    assert store.attend_recent() == []


def test_a_spawn_that_raises_leaves_the_job_published(attending: Configure):
    """The watch on a stopped run must not itself be able to stop."""
    attending()

    def _explode(job: attend.AttendJob) -> None:
        raise OSError("no claude here")

    assert _gate(spawner=_explode) is not None
    assert len(attend.queue()) == 1


def test_a_job_carries_the_gate_body_verbatim(attending: Configure):
    """Three incompatible gate formats are in the tree; handing the text over intact
    is the only thing that covers all of them."""
    spawner = attending()
    body = "## Blocked\n\n- tried: reload\n- tried: answer\n"
    job = _gate(spawner=spawner, question=body)
    assert job is not None and body in job.prompt()


def test_the_doctrine_ships_with_groom(attending: Configure):
    """The prompt is groom's own package data, not a base-library lookup: an attendant
    dispatched on a machine with no library configured must still get the rules, since
    the facts without the rules is exactly the attendant that answers a gate to move a
    run."""
    spawner = attending()
    job = _gate(spawner=spawner)
    assert job is not None
    assert attend.PROMPT_PATH.is_file()
    assert "Never answer a gate to make the run move" in job.prompt()


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


def test_a_dead_run_is_routed_by_the_class_it_recorded(attending: Configure, tmp_path):
    """This half has the machine-readable class the gates lack — read it, don't parse prose."""
    spawner = attending()
    job = attend.attend_death(
        run_id="r1", workflow="okf-builder", run_dir=_failure_run(tmp_path),
        workspace="/repo", now=0.0, spawner=spawner,
    )
    assert job is not None
    assert (job.failure_class, job.node) == ("AgentTurnFailed", "adjudicate")
    assert "boom" in job.prompt()


def test_a_run_that_left_no_handoff_is_still_attended(attending: Configure, tmp_path):
    """A SIGKILL writes nothing; the empty class is what sends it to the checkpoint."""
    spawner = attending()
    job = attend.attend_death(
        run_id="r1", workflow="okf-builder", run_dir=str(tmp_path), workspace="/repo",
        now=0.0, spawner=spawner,
    )
    assert job is not None and job.failure_class == ""
    assert "checkpoint.json" in job.prompt()


# ---- the table -----------------------------------------------------------------
def test_a_row_is_running_until_the_owner_finishes_it(attending: Configure):
    """Two states, and no third: an attendant sends no heartbeat, so there is nothing
    a middle state could mean."""
    attending()
    store.attend_start("j1", run_id="r1", workflow="okf-builder", kind="gate",
                       session_id="s1", pid=99, started_at=100.0)
    running = store.attend_running_for_run("r1")
    assert running is not None and running["status"] == store.ATTEND_RUNNING
    assert running["session_ids"] == ["s1"]
    store.attend_finish("j1", exit_code=0, released_state="ANSWERED")
    assert store.attend_running_for_run("r1") is None
    latest = store.attend_latest_for_run("r1")
    assert latest is not None
    assert (latest["status"], latest["exit_code"], latest["released_state"]) == (
        store.ATTEND_COMPLETED, 0, "ANSWERED",
    )


def test_a_second_attempt_appends_to_the_row_it_already_has(attending: Configure):
    """Boot recovery is the same attendance continuing, so the history is one row."""
    attending()
    store.attend_start("j1", run_id="r1", session_id="s1", pid=1, started_at=1.0)
    store.attend_finish("j1", exit_code=None, released_state="")
    store.attend_append_session("j1", "s2", pid=2)
    row = store.attend_get("j1")
    assert row is not None
    assert row["session_ids"] == ["s1", "s2"]
    assert (row["status"], row["pid"], row["exit_code"]) == (store.ATTEND_RUNNING, 2, None)
    assert store.attend_by_session("s1") == row
    assert [orphan["job_id"] for orphan in store.attend_orphans()] == ["j1"]


def test_the_log_is_newest_first_and_nothing_is_pruned(attending: Configure):
    """200 latest, most recent first — create-once, keep-forever."""
    attending()
    for index in range(5):
        store.attend_start(f"j{index}", run_id=f"r{index}", started_at=float(index))
    assert [row["job_id"] for row in store.attend_recent()] == ["j4", "j3", "j2", "j1", "j0"]
    assert [row["job_id"] for row in store.attend_recent(2)] == ["j4", "j3"]
    assert list(store.attend_latest_by_run()) == ["r0", "r1", "r2", "r3", "r4"]


# ---- the process groom owns ----------------------------------------------------
def test_the_row_is_written_before_the_first_byte_and_flipped_at_exit(
    attending: Configure, monkeypatch: pytest.MonkeyPatch,
):
    """The session id is minted, not scraped, so the row can exist from the spawn.

    A groom that died one second after the dispatch otherwise leaves a claude nobody
    can name — and boot recovery has nothing to find.
    """
    attending()
    proc = _FakeProc(code=0)
    minted: list[str] = []

    def _launch(job: attend.AttendJob, session_id: str) -> Any:
        minted.append(session_id)
        return proc

    monkeypatch.setattr(attend, "_launch", _launch)
    job = _gate(spawner=None)
    assert job is not None
    row = store.attend_get(job.job_id)
    assert row is not None
    assert (row["status"], row["pid"]) == (store.ATTEND_RUNNING, proc.pid)
    assert row["session_ids"] == minted != [""]

    proc.done.set()
    _await(
        lambda: (store.attend_get(job.job_id) or {}).get("status") == store.ATTEND_COMPLETED,
        "the owning thread to close the row",
    )
    assert (store.attend_get(job.job_id) or {})["exit_code"] == 0
    # The run is handed back, so the next announcement of a *new* stop dispatches.
    assert attend.queue() == []


def _sleeper() -> subprocess.Popen[bytes]:
    """A process of its own group, so the whole group can be signalled like a real one."""
    return subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True
    )


def test_stop_hard_kills_the_attendant_and_hands_the_run_back(attending: Configure):
    """Not a way to abandon a run — a way to take it back to your own terminal."""
    attending()
    proc = _sleeper()
    try:
        store.attend_start("j1", run_id="r1", kind="gate", session_id="s1",
                           pid=proc.pid, started_at=0.0)
        assert attend.stop("j1") is True
        assert proc.wait(timeout=WAIT_S) != 0
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=WAIT_S)
    row = store.attend_get("j1")
    assert row is not None
    assert (row["status"], row["released_state"]) == (store.ATTEND_COMPLETED, "stopped")
    # A row that is already finished is not something to kill twice.
    assert attend.stop("j1") is False


def test_boot_recovery_restarts_a_dead_pid_into_the_same_row(
    attending: Configure, monkeypatch: pytest.MonkeyPatch,
):
    """A groom restart kills its attendants and claude sends no heartbeat, so a row
    still saying ``running`` is the only trace. It is re-run, not re-filed."""
    attending()
    dead = subprocess.Popen([sys.executable, "-c", ""])
    dead.wait(timeout=WAIT_S)
    store.attend_start("j1", run_id="r1", workflow="okf-builder", kind="gate",
                       run_dir="/runs/r1", workspace="/repo", session_id="s1",
                       pid=dead.pid, started_at=0.0)
    alive = _sleeper()
    try:
        store.attend_start("j2", run_id="r2", kind="gate", session_id="s2",
                           pid=alive.pid, started_at=1.0)
        proc = _FakeProc(pid=777)
        monkeypatch.setattr(attend, "_launch", lambda job, session_id: proc)
        assert attend.recover_orphans() == 1
    finally:
        alive.kill()
        alive.wait(timeout=WAIT_S)

    row = store.attend_get("j1")
    assert row is not None
    assert len(row["session_ids"]) == 2 and row["session_ids"][0] == "s1"
    assert (row["status"], row["pid"]) == (store.ATTEND_RUNNING, 777)
    # One attendance, not two: the run is still the same stopped run.
    assert len(store.attend_recent()) == 2
    # And the restarted attendant is owned, so its exit closes the row it re-armed.
    proc.done.set()
    _await(
        lambda: (store.attend_get("j1") or {}).get("status") == store.ATTEND_COMPLETED,
        "the recovered attendant to close its row",
    )


# ---- reading one back ----------------------------------------------------------
def _transcript(session_id: str, records: list[dict[str, Any]], sidechain=None) -> None:
    directory = attend_transcript.session_dir(session_id)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{session_id}.jsonl").write_text(
        "\n".join(json.dumps(record) for record in records) + "\n"
    )
    if sidechain is not None:
        nested = directory / session_id
        nested.mkdir(parents=True, exist_ok=True)
        (nested / "sub.jsonl").write_text(
            "\n".join(json.dumps(record) for record in sidechain) + "\n"
        )


def _turn(role: str, content: Any) -> dict[str, Any]:
    return {"type": role, "message": {"role": role, "content": content}}


_MAIN = [
    _turn("user", "Attend this gate."),
    _turn("assistant", [
        {"type": "thinking", "thinking": "not what it did, and not what it said"},
        {"type": "text", "text": "Reading the gate first."},
        {"type": "tool_use", "id": "t1", "name": "Read",
         "input": {"file_path": "/runs/r1/docs/gate.md", "limit": 40}},
    ]),
    _turn("user", [{"type": "tool_result", "tool_use_id": "t1", "content": "STATUS: AWAITING"}]),
    _turn("assistant", [{"type": "text", "text": "Declining: this is a credential wall."}]),
]


def test_a_session_reads_back_as_a_conversation(attending: Configure):
    """The pane shows what an attendant did and said, the way a terminal would.

    Not a JSON viewer: prose is prose, a tool call is one line carrying its arguments
    and its result, and reasoning is neither of those.
    """
    attending()
    _transcript("sess-1", _MAIN, sidechain=[_turn("assistant", [{"type": "text", "text": "sub"}])])
    rendered = attend_transcript.render_session("sess-1")
    assert rendered["present"] is True
    kinds = [(entry["kind"], entry.get("role") or entry.get("name") or entry.get("label"))
             for entry in rendered["entries"]]
    assert kinds[:4] == [
        ("message", "user"), ("message", "assistant"), ("tool", "Read"), ("message", "assistant"),
    ]
    assert kinds[4][0] == "divider"
    assert kinds[5] == ("message", "assistant")
    call = rendered["entries"][2]
    assert call["summary"] == "Read: /runs/r1/docs/gate.md"
    assert "limit: 40" in call["detail"]
    assert call["result"] == "STATUS: AWAITING" and call["failed"] is False
    assert rendered["entries"][5]["sidechain"] is True
    assert all("thinking" not in json.dumps(entry) for entry in rendered["entries"])


def test_a_session_with_nothing_copied_renders_empty_rather_than_raising(
    attending: Configure,
):
    """A transcript that could not be copied is a poorer record, not a failed attendance."""
    attending()
    rendered = attend_transcript.render_session("missing")
    assert rendered == {
        "session_id": "missing", "present": False,
        "path": str(attend_transcript.session_dir("missing")), "entries": [],
    }


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


def test_an_exit_that_is_a_death_dispatches_and_a_reload_does_not(
    attending: Configure, tmp_path,
):
    """Exit 3 is the supervisor restarting the run on purpose — not something to attend."""
    attending(attend.SESSION)
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


def test_the_queue_endpoint_lists_the_fleet(attending: Configure):
    """One endpoint for every outstanding job, rather than one watch loop per run id."""
    attending(attend.SESSION)
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


def test_the_sessions_endpoint_is_the_log_the_pane_renders(attending: Configure):
    """Newest first, with the mode beside it — the pane says what it is looking at."""
    attending(attend.SESSION)
    _reset_fleet()
    store.attend_start("j1", run_id="r1", workflow="okf-builder", kind="gate",
                       reason="parked", session_id="s1", started_at=1.0)
    store.attend_start("j2", run_id="r2", workflow="coder", kind="death",
                       session_id="s2", started_at=2.0)
    client = _client()
    try:
        payload = client.get("/api/attend/sessions").json()
    finally:
        client.__exit__(None, None, None)
    assert payload["mode"] == "session"
    assert [row["job_id"] for row in payload["sessions"]] == ["j2", "j1"]
    assert payload["sessions"][1]["session_ids"] == ["s1"]


def test_one_session_comes_back_with_a_pasteable_resume_line(attending: Configure):
    """The point of keeping these is being able to go ask the attendant what it thought,
    and that needs the workspace as much as the session id."""
    attending(attend.SESSION)
    _reset_fleet()
    store.attend_start("j1", run_id="r1", workflow="okf-builder", kind="gate",
                       workspace="/repo", session_id="s1", started_at=1.0)
    store.attend_append_session("j1", "s2", pid=5)
    _transcript("s2", _MAIN)
    client = _client()
    try:
        payload = client.get("/api/attend/sessions/s2").json()
    finally:
        client.__exit__(None, None, None)
    assert payload["resume"] == "cd /repo && claude --resume s2"
    assert payload["attempts"] == ["s1", "s2"]
    assert payload["record"]["job_id"] == "j1"
    assert payload["entries"][0]["text"] == "Attend this gate."


def test_the_stop_endpoint_kills_the_attendant(attending: Configure):
    """The Stop button is the operator saying they will work this run themselves."""
    attending(attend.SESSION)
    _reset_fleet()
    proc = _sleeper()
    try:
        store.attend_start("j1", run_id="r1", kind="gate", pid=proc.pid, started_at=0.0)
        client = _client()
        try:
            assert client.post("/api/attend/sessions/j1/stop").json() == {"ok": True}
            assert client.post("/api/attend/sessions/nope/stop").json() == {"ok": False}
        finally:
            client.__exit__(None, None, None)
        assert proc.wait(timeout=WAIT_S) != 0
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=WAIT_S)
    assert (store.attend_get("j1") or {})["status"] == store.ATTEND_COMPLETED


def test_the_settings_endpoint_persists_the_toggle_to_the_home_config(
    attending: Configure, tmp_path,
):
    """Off is stored as itself, and on restores the mode that was last in use — an
    operator running `session` who toggles off and on does not get a claude back."""
    attending(attend.SESSION)
    _reset_fleet()
    client = _client()
    try:
        before = client.get("/api/settings/attend").json()
        assert (before["mode"], before["sources"]["mode"]) == ("session", "environment")

        off = client.post("/api/settings/attend", json={"enabled": False}).json()
        assert (off["mode"], off["last_mode"], off["sources"]["mode"]) == (
            "off", "session", "config",
        )
        assert attend.mode() == attend.OFF

        back = client.post("/api/settings/attend", json={"enabled": True}).json()
        assert back["mode"] == "session"
    finally:
        client.__exit__(None, None, None)
    assert "session" in (tmp_path / "config.toml").read_text()


def test_a_container_row_is_not_attended_from_this_host(attending: Configure):
    """Its `runs_volume` is a docker volume name — an attendant here has nothing to open."""
    attending(attend.SESSION)
    _reset_fleet()
    row = _native_row()
    row.native = False
    row.gates["docs/gate.md"] = GateInfo(workflow_id="r1", file_path="docs/gate.md")
    state.WORKFLOWS["r1"] = row
    groom_app._attend_gates(row, list(row.gates.values()))
    assert attend.queue() == []


def test_gates_clearing_releases_the_run(attending: Configure):
    """A row with no gates is a run that is going again, whoever cleared it."""
    attending(attend.SESSION)
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



def test_a_gate_the_hint_already_armed_is_still_attended(attending: Configure):
    """The announcement writes the row, *then* fires the poll that dispatches.

    `/push/blocked`, the native checkpoint sync and the sidecar snapshot all set
    `wf.gates[file_path]` before calling `_poll_gate_soon`, so by the time the poll
    runs, the gate the run is parked on is already on the row and nothing about it is
    "fresh". Dispatching on freshness therefore skipped the primary path entirely and
    a parked run got no attendant at all.
    """
    attending(attend.SESSION)
    _reset_fleet()
    row = _native_row()
    # Exactly what `_apply_socket_blocked` / `/push/blocked` write before the poll.
    row.gates["docs/gate.md"] = GateInfo(
        workflow_id="r1", file_path="docs/gate.md", question="Q?"
    )
    row.state = WorkflowState.BLOCKED
    state.WORKFLOWS["r1"] = row

    reply = {
        "ok": True,
        "questions": [{"path": "docs/gate.md", "question": "Q?", "kind": "operator"}],
    }
    with patch.object(groom_app, "_gate_pollable", return_value=True), \
         patch.object(groom_app, "_socket_questions", AsyncMock(return_value=reply)), \
         patch.object(groom_app, "_broadcast_shell", AsyncMock()), \
         patch.object(groom_app, "_broadcast_notify", AsyncMock()):
        asyncio.run(groom_app._poll_gates_of("r1"))

    assert [job["gate_path"] for job in attend.queue()] == ["/repo/docs/gate.md"]


def test_the_poll_never_dispatches_at_a_machine_wait(attending: Configure):
    """The run's own listing carries `kind`, and that is the only reason this is safe.

    The poll now offers every reported gate rather than the new ones, so the guard
    that a measurement is not a stopped run has to hold on the repeated offer too.
    """
    attending(attend.SESSION)
    _reset_fleet()
    row = _native_row()
    row.gates["docs/gate.md"] = GateInfo(
        workflow_id="r1", file_path="docs/gate.md", question="Q?"
    )
    state.WORKFLOWS["r1"] = row

    reply = {
        "ok": True,
        "questions": [{"path": "docs/gate.md", "question": "Q?", "kind": "machine"}],
    }
    with patch.object(groom_app, "_gate_pollable", return_value=True), \
         patch.object(groom_app, "_socket_questions", AsyncMock(return_value=reply)), \
         patch.object(groom_app, "_broadcast_shell", AsyncMock()), \
         patch.object(groom_app, "_broadcast_notify", AsyncMock()):
        asyncio.run(groom_app._poll_gates_of("r1"))

    assert attend.queue() == []


def test_a_run_still_parked_on_the_same_gate_collects_one_attendant(
    attending: Configure,
):
    """Ten reconciling ticks over a stall are ten offers and still one claude."""
    attending(attend.SESSION)
    _reset_fleet()
    row = _native_row()
    state.WORKFLOWS["r1"] = row
    reply = {
        "ok": True,
        "questions": [{"path": "docs/gate.md", "question": "Q?", "kind": "operator"}],
    }
    with patch.object(groom_app, "_gate_pollable", return_value=True), \
         patch.object(groom_app, "_socket_questions", AsyncMock(return_value=reply)), \
         patch.object(groom_app, "_broadcast_shell", AsyncMock()), \
         patch.object(groom_app, "_broadcast_notify", AsyncMock()):
        for _ in range(10):
            asyncio.run(groom_app._poll_gates_of("r1"))

    assert len(attend.queue()) == 1


def test_the_dispatched_gate_path_is_absolute(attending: Configure):
    """`GateInfo.file_path` is workspace-relative; the attendant leaves the process with it.

    Two consumers open `gate_path` as a filesystem path — the job body, and `_first_status`
    at exit for the released `STATUS:`. A relative one resolves against *groom's own* cwd,
    which is right only when groom happens to serve the repo the run lives in and silently
    wrong for every other repo in the fleet: the gate reads as empty and the attendance
    records no outcome.
    """
    attending(attend.SESSION)
    _reset_fleet()
    row = _native_row()
    row.state = WorkflowState.BLOCKED
    state.WORKFLOWS["r1"] = row
    reply = {
        "ok": True,
        "questions": [{"path": "docs/gate.md", "question": "Q?", "kind": "operator"}],
    }
    with patch.object(groom_app, "_gate_pollable", return_value=True), \
         patch.object(groom_app, "_socket_questions", AsyncMock(return_value=reply)), \
         patch.object(groom_app, "_broadcast_shell", AsyncMock()), \
         patch.object(groom_app, "_broadcast_notify", AsyncMock()):
        asyncio.run(groom_app._poll_gates_of("r1"))

    assert [job["gate_path"] for job in attend.queue()] == ["/repo/docs/gate.md"]


def test_the_prompt_carries_the_whole_gate_not_the_dashboard_preview(tmp_path):
    """`extract_question` keeps one section and truncates it to 4000 characters.

    That is the right shape for a row in a table and the wrong shape for the only copy
    the attendant gets: a long adjudication arrives cut mid-word with most of its
    findings missing, and an attendant cannot fix a finding it was never shown.
    """
    gate = tmp_path / "gate.md"
    body = "\n".join(f"- finding {i}: {'x' * 200}" for i in range(60))
    gate.write_text(f"STATUS: AWAITING_OPERATOR\n\n## Questions from the agent\n\n{body}\n")
    preview = gates.extract_question(gate.read_text())
    assert len(preview) == 4000  # the defect: the tail is gone before the job is built

    job = attend.AttendJob(
        job_id="j1", run_id="r1", kind="gate", workflow="okf-builder",
        run_dir="/runs/r1", workspace=str(tmp_path), created_at=0.0,
        gate_path=str(gate), question=preview,
    )
    assert "finding 59" in job.facts()


def test_the_gate_body_falls_back_to_the_preview_when_the_file_is_gone(tmp_path):
    """A gate answered or moved between the dispatch and the read still says something."""
    job = attend.AttendJob(
        job_id="j1", run_id="r1", kind="gate", workflow="okf-builder",
        run_dir="/runs/r1", workspace=str(tmp_path), created_at=0.0,
        gate_path=str(tmp_path / "vanished.md"), question="What now?",
    )
    assert job.gate_body() == "What now?"


def test_the_prompt_hands_over_the_groom_reads(tmp_path):
    """The attendant is dispatched by groom and the run's history is already on disk.

    Without the commands it opens source files instead of reading what the run itself
    recorded while it was failing — which is the half the gate body leaves out.
    """
    job = attend.AttendJob(
        job_id="j1", run_id="r1", kind="gate", workflow="okf-builder",
        run_dir="/runs/r1", workspace=str(tmp_path), created_at=0.0,
        gate_path="", question="What now?",
    )
    prompt = job.prompt()
    for read in ("groom logs --run", "groom loops --run", "groom transcript ls --run"):
        assert read in prompt
