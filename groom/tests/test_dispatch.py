"""groom's dispatch queues: config-declared lanes, capped at their own concurrency.

No agent process here either (see `test_attend.py`'s own note): every launch is faked
with a process this test controls the exit of, and the one process actually spawned
(`test_stop_kills_a_running_item_and_frees_its_slot`) is a sleeper this test kills.

Run: uv run pytest groom/tests/test_dispatch.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from litestar.testing import TestClient

from groom import app as groom_app
from groom import dispatch, discovery, state, store

WAIT_S = 5.0


class _FakeProc:
    """A process that ends when the test says so, and never before."""

    def __init__(self, pid: int = 4242, code: int = 0) -> None:
        self.pid = pid
        self.code = code
        self.done = threading.Event()

    def wait(self) -> int:
        self.done.wait(WAIT_S)
        return self.code


def _write_config(tmp_path: Path, queues: dict[str, dict[str, Any]]) -> None:
    lines: list[str] = []
    for name, opts in queues.items():
        lines.append(f"[groom.dispatch.{name}]")
        lines.append(f'command = "{opts["command"]}"')
        if "concurrency" in opts:
            lines.append(f"concurrency = {opts['concurrency']}")
        for param in opts.get("params", []):
            lines.append(f"[[groom.dispatch.{name}.params]]")
            for key, value in param.items():
                if isinstance(value, bool):
                    lines.append(f"{key} = {str(value).lower()}")
                elif isinstance(value, list):
                    rendered = ", ".join(f'"{item}"' for item in value)
                    lines.append(f"{key} = [{rendered}]")
                else:
                    lines.append(f'{key} = "{value}"')
    (tmp_path / "config.toml").write_text("\n".join(lines) + "\n")


Configure = Callable[..., None]


@pytest.fixture
def dispatching(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Configure]:
    """A groom whose database and config are this test's own, with no queue slot
    left over from a previous test's concurrency (see `dispatch.reset`)."""

    def _configure(**queues: dict[str, Any]) -> None:
        monkeypatch.setenv("GROOM_DB", str(tmp_path / "groom.db"))
        monkeypatch.setenv("STABLEMATE_CONFIG", str(tmp_path / "config.toml"))
        _write_config(tmp_path, queues)
        store.reset()
        dispatch.reset()

    yield _configure
    store.reset()
    dispatch.reset()


def _await(predicate: Callable[[], bool], what: str) -> None:
    """Spin until the owning thread has done its work, or say what never happened."""
    deadline = time.monotonic() + WAIT_S
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError(f"timed out waiting for {what}")


def _sleeper() -> subprocess.Popen[bytes]:
    """A process of its own group, so the whole group can be signalled like a real one."""
    return subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True
    )


def _status(item_id: str) -> str:
    row = store.dispatch_get(item_id)
    assert row is not None
    return row["status"]


# ---- enqueue & concurrency -------------------------------------------------------
def test_unknown_queue_raises_rather_than_being_minted(dispatching: Configure):
    """A queue is declared by config, never created by the first thing enqueued at it."""
    dispatching()
    with pytest.raises(dispatch.UnknownQueue):
        dispatch.enqueue("no-such-queue")


def test_a_burst_past_capacity_runs_only_k_and_leaves_the_rest_pending(
    dispatching: Configure, monkeypatch: pytest.MonkeyPatch,
):
    """Five items at a queue capped at two: two `running`, three still `pending`."""
    dispatching(q=dict(command="workhorse-loop-runner", concurrency=2))
    procs = [_FakeProc(pid=100 + i) for i in range(5)]
    calls: list[str] = []

    def _launch(item_id: str, command: str, params: dict[str, Any]) -> _FakeProc:
        calls.append(item_id)
        return procs[len(calls) - 1]

    monkeypatch.setattr(dispatch, "_launch", _launch)
    items = [dispatch.enqueue("q") for _ in range(5)]
    ids = [item["item_id"] for item in items]

    _await(lambda: len(calls) == 2, "exactly two items to launch")
    rows = {row["item_id"]: row["status"] for row in store.dispatch_list("q")}
    running = [i for i in ids if rows[i] == store.DISPATCH_RUNNING]
    pending = [i for i in ids if rows[i] == store.DISPATCH_PENDING]
    assert (len(running), len(pending)) == (2, 3)

    # Finishing one running item frees a slot the drain hands to the next pending one.
    procs[0].done.set()
    _await(lambda: len(calls) == 3, "a third item to launch once a slot frees")
    for proc in procs[1:]:
        proc.done.set()
    _await(
        lambda: all(
            row["status"] in (store.DISPATCH_DONE, store.DISPATCH_FAILED)
            or row["item_id"] == ids[0]
            for row in store.dispatch_list("q")
        ),
        "every launched item to finish",
    )


def test_two_queues_with_the_same_command_are_independent(
    dispatching: Configure, monkeypatch: pytest.MonkeyPatch,
):
    """One queue at capacity does not borrow or block on the other's slots."""
    dispatching(
        a=dict(command="workhorse-loop-runner", concurrency=1),
        b=dict(command="workhorse-loop-runner", concurrency=1),
    )
    procs = {"a": _FakeProc(pid=1), "b": _FakeProc(pid=2)}
    launched: list[str] = []

    def _launch(item_id: str, command: str, params: dict[str, Any]) -> _FakeProc:
        queue_name = "a" if len(launched) == 0 else "b"
        launched.append(item_id)
        return procs[queue_name]

    monkeypatch.setattr(dispatch, "_launch", _launch)
    item_a = dispatch.enqueue("a")
    item_b = dispatch.enqueue("b")

    _await(lambda: len(launched) == 2, "both queues to launch independently")
    assert _status(item_a["item_id"]) == store.DISPATCH_RUNNING
    assert _status(item_b["item_id"]) == store.DISPATCH_RUNNING

    procs["a"].done.set()
    procs["b"].done.set()


# ---- cancel & stop ----------------------------------------------------------------
def test_cancelling_a_pending_item_never_spawns_it(
    dispatching: Configure, monkeypatch: pytest.MonkeyPatch,
):
    """A queue at capacity: the item behind it is dropped before its turn ever comes."""
    dispatching(q=dict(command="workhorse-loop-runner", concurrency=1))
    holder = _FakeProc(pid=1)
    monkeypatch.setattr(dispatch, "_launch", lambda item_id, command, params: holder)

    first = dispatch.enqueue("q")
    second = dispatch.enqueue("q")
    assert _status(second["item_id"]) == store.DISPATCH_PENDING

    assert dispatch.cancel_pending(second["item_id"]) is True
    assert _status(second["item_id"]) == store.DISPATCH_CANCELLED
    # Already-terminal or already-running is not cancel_pending's job.
    assert dispatch.cancel_pending(first["item_id"]) is False

    holder.done.set()
    _await(
        lambda: _status(first["item_id"]) != store.DISPATCH_RUNNING,
        "the running item to finish",
    )
    # The cancelled item is never launched, even after a slot frees up.
    assert _status(second["item_id"]) == store.DISPATCH_CANCELLED


def test_stop_kills_a_running_item_and_frees_its_slot(dispatching: Configure):
    """Not a way to abandon an item — it flips terminal and its slot is handed onward."""
    dispatching(q=dict(command="workhorse-loop-runner", concurrency=1))
    store.dispatch_enqueue("i1", queue="q", command="workhorse-loop-runner", params={})
    proc = _sleeper()
    dispatch._slot("q", 1).acquire()
    store.dispatch_start("i1", run_id="i1", pid=proc.pid)
    try:
        assert dispatch.stop("i1") is True
        assert proc.wait(timeout=WAIT_S) != 0
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=WAIT_S)
    row = store.dispatch_get("i1")
    assert row is not None
    assert row["status"] == store.DISPATCH_CANCELLED
    # A row that already finished is not something to stop twice.
    assert dispatch.stop("i1") is False
    # The slot came back: a fresh acquire does not block.
    assert dispatch._slot("q", 1).acquire(blocking=False) is True


# ---- boot recovery ------------------------------------------------------------
def test_boot_recovery_leaves_an_alive_item_running_and_fails_a_dead_one(
    dispatching: Configure,
):
    """Alive → the row is still true, groom just isn't watching it anymore. Dead → the
    row is closed `failed`, never relaunched (unlike `attend`'s own boot recovery)."""
    dispatching()
    alive = _sleeper()
    dead = subprocess.Popen([sys.executable, "-c", ""])
    dead.wait(timeout=WAIT_S)
    try:
        store.dispatch_enqueue("i1", queue="q", command="workhorse-loop-runner", params={})
        store.dispatch_start("i1", run_id="i1", pid=alive.pid)
        store.dispatch_enqueue("i2", queue="q", command="workhorse-loop-runner", params={})
        store.dispatch_start("i2", run_id="i2", pid=dead.pid)

        assert dispatch.recover_orphans() == 1

        assert _status("i1") == store.DISPATCH_RUNNING
        assert _status("i2") == store.DISPATCH_FAILED
    finally:
        alive.kill()
        alive.wait(timeout=WAIT_S)


def test_boot_recovery_seeds_the_slot_so_the_cap_still_holds(
    dispatching: Configure, monkeypatch: pytest.MonkeyPatch,
):
    """An alive orphan left `running` still occupies a real slot somewhere — a fresh
    process must not hand out its queue's full concurrency on top of it."""
    dispatching(q=dict(command="workhorse-loop-runner", concurrency=2))
    alive = _sleeper()
    try:
        store.dispatch_enqueue("orphan", queue="q", command="workhorse-loop-runner", params={})
        store.dispatch_start("orphan", run_id="orphan", pid=alive.pid)
        assert dispatch.recover_orphans() == 0

        procs = [_FakeProc(pid=200 + i) for i in range(2)]
        calls: list[str] = []

        def _launch(item_id: str, command: str, params: dict[str, Any]) -> _FakeProc:
            calls.append(item_id)
            return procs[len(calls) - 1]

        monkeypatch.setattr(dispatch, "_launch", _launch)
        items = [dispatch.enqueue("q") for _ in range(2)]
        ids = [item["item_id"] for item in items]

        # The orphan already holds one of this queue's two slots, so only one of the
        # two freshly-enqueued items may launch — not both.
        _await(lambda: len(calls) == 1, "only one new item to launch alongside the orphan")
        time.sleep(0.1)
        assert len(calls) == 1
        rows = {row["item_id"]: row["status"] for row in store.dispatch_list("q")}
        assert sorted(rows[i] for i in ids) == [store.DISPATCH_PENDING, store.DISPATCH_RUNNING]

        procs[0].done.set()
    finally:
        alive.kill()
        alive.wait(timeout=WAIT_S)


# ---- the app edges --------------------------------------------------------------
def _client() -> TestClient:
    with patch.object(discovery, "scan", return_value=[]), \
         patch.object(discovery, "present_container_ids", return_value=None):
        client = TestClient(app=groom_app.create_app())
        client.__enter__()
    return client


def _reset_fleet() -> None:
    state.WORKFLOWS.clear()
    state.RUNS.clear()
    state.SCANNING = False


def test_get_queues_reports_concurrency_and_occupancy_under_load(
    dispatching: Configure, monkeypatch: pytest.MonkeyPatch,
):
    """The one endpoint the dashboard pane and `groom dispatch queues` both read."""
    dispatching(q=dict(command="workhorse-loop-runner", concurrency=2))
    # `create_app()` below runs its own boot-recovery pass, which would fail a
    # `running` row whose pid is not actually alive — so these fakes borrow this
    # test process's own, very much alive, pid.
    procs = [_FakeProc(pid=os.getpid()) for _ in range(3)]
    calls: list[str] = []

    def _launch(item_id: str, command: str, params: dict[str, Any]) -> _FakeProc:
        calls.append(item_id)
        return procs[len(calls) - 1]

    monkeypatch.setattr(dispatch, "_launch", _launch)
    for _ in range(3):
        dispatch.enqueue("q")
    _await(lambda: len(calls) == 2, "two items to launch at the configured cap")

    _reset_fleet()
    client = _client()
    try:
        resp = client.get("/api/dispatch/queues")
        assert resp.status_code == 200
        rows = {row["name"]: row for row in resp.json()["queues"]}
        assert rows["q"]["concurrency"] == 2
        assert rows["q"]["running"] == 2
        assert rows["q"]["command"] == "workhorse-loop-runner"
    finally:
        client.__exit__(None, None, None)
        for proc in procs:
            proc.done.set()


# ---- params schema & templates ---------------------------------------------------
def test_queue_status_exposes_the_configured_params_schema(dispatching: Configure):
    """The dashboard's enqueue form renders straight off this — no hardcoded fields."""
    dispatching(
        q=dict(
            command="workhorse-loop-runner",
            params=[
                dict(name="plan", label="Plan path", required=True),
                dict(name="cli", label="Agent CLI", type="select", options=["claude", "codex"]),
            ],
        )
    )
    rows = dispatch.queue_status()
    row = next(r for r in rows if r["name"] == "q")
    params = {p["name"]: p for p in row["params"]}
    assert params["plan"]["label"] == "Plan path"
    assert params["plan"]["required"] is True
    assert params["cli"]["type"] == "select"
    assert params["cli"]["options"] == ["claude", "codex"]
    # `template` is a launch-time detail, not something the form needs to see.
    assert "template" not in params["plan"]


def test_enqueue_expands_a_param_with_a_template_before_storing_it(
    dispatching: Configure, monkeypatch: pytest.MonkeyPatch,
):
    """A queue-config `template` composes the operator's raw input into whatever the
    target workflow's prompt actually needs — no per-workflow logic in `dispatch.py`."""
    dispatching(
        q=dict(
            command="workhorse-loop-runner",
            params=[
                dict(
                    name="plan",
                    label="Plan path",
                    template="/goal implement all phases of plan {value}. Commit your work before finishing",
                )
            ],
        )
    )
    monkeypatch.setattr(dispatch, "_launch", lambda item_id, command, params: _FakeProc())
    item = dispatch.enqueue("q", {"plan": "docs/plans/x.md"})
    assert item["params"]["plan"] == (
        "/goal implement all phases of plan docs/plans/x.md. Commit your work before finishing"
    )


def test_launch_forwards_cli_as_its_own_flag_not_inside_params(
    dispatching: Configure, monkeypatch: pytest.MonkeyPatch,
):
    """`--cli` is `workhorse run`'s own flag, not a workflow param — a `cli` key in the
    enqueue params must not leak into the `--params` JSON blob `_launch` builds."""
    dispatching(q=dict(command="workhorse-loop-runner"))
    captured: dict[str, Any] = {}

    class _FakeSupervisor:
        def spawn(self, argv: list[str], *_args: Any, **_kwargs: Any) -> _FakeProc:
            captured["argv"] = argv
            return _FakeProc()

    monkeypatch.setattr(dispatch, "ProcessSupervisor", _FakeSupervisor)
    dispatch._launch("item1", "workhorse-loop-runner", {"plan": "x", "cli": "codex"})
    argv = captured["argv"]
    assert "--cli" in argv
    assert argv[argv.index("--cli") + 1] == "codex"
    params_json = argv[argv.index("--params") + 1]
    assert "cli" not in json.loads(params_json)
