"""App-level tests for the new liveness handlers: the /push/exited endpoint,
the deletion half of /refresh (prune), and the answered-gate state flip +
groom:answered broadcast in _handle_command. Docker and the answer write are
mocked so nothing shells out.

Run: uv run pytest tests/test_app.py
"""
from __future__ import annotations

import asyncio
import contextlib
import inspect
import tempfile
from pathlib import Path
from unittest.mock import patch

from litestar.testing import TestClient

from groom import app as groom_app
from groom import discovery, sidecar_hub, state
from groom.models import AnswerResult, GateInfo, WorkflowContainer, WorkflowState
from workhorse import inbox


def _reset() -> None:
    state.WORKFLOWS.clear()
    # The telemetry cache is upstream of the rows: `_live_loop` re-syncs a native row
    # from every entry in RUNS on each tick, so a run another file left here is
    # re-materialized into WORKFLOWS *after* this reset and shows up in the broadcast.
    # Clearing the rows alone makes the fleet cases order-dependent.
    state.RUNS.clear()
    state._gate_locks.clear()
    state.CLIENTS.clear()
    state.WATCHING.clear()
    sidecar_hub.CONNECTIONS.clear()
    # Discovery-in-progress is fleet state too. SCANNING defaults to True at
    # import, and every `_hermetic_client()` starts a background scan that
    # clears it whenever the loop next gets a turn — so a case that projects
    # the fleet twice can otherwise catch the flag on either side of that flip
    # and see two legitimately different payloads.
    state.SCANNING = False


class _NoSocket:
    """The socket a `_FakeConn` will never send on — its two RPCs are canned."""

    async def send_json(self, data) -> None:
        raise AssertionError("a _FakeConn answers without sending on a socket")


class _FakeConn(sidecar_hub.SidecarConnection):
    """A stand-in sidecar connection registered directly into the hub, so the
    data-plane handlers exercise the socket-preferred path without a real
    WebSocket.

    A real `SidecarConnection` and not a look-alike: the hub's registry is a dict of
    them, and what this replaces is the two coroutines a handler awaits, not the
    type the handler is handed."""

    def __init__(self, container_id: str, *, result=None, error: bool = False) -> None:
        super().__init__(container_id, _NoSocket())
        self._result = result
        self._error = error
        self.reloaded = False

    async def rpc(self, method: str, params: dict, *, timeout: float = 0.0):
        if self._error:
            raise sidecar_hub.SidecarError("socket unavailable")
        return self._result

    async def send_reload(self) -> None:
        self.reloaded = True


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


# ---- the notify frame: an edge, on its own frame, carrying no markup ----
def test_push_blocked_sends_the_state_frame_then_a_separate_notify_frame():
    _reset()
    wf = WorkflowContainer(
        container_id="abc123", name="coder-acme", state=WorkflowState.RUNNING, workspace_volume="v"
    )
    state.WORKFLOWS["abc123"] = wf

    captured: list[dict] = []

    async def _capture_broadcast(message):
        captured.append(message)

    with patch.object(state, "broadcast", _capture_broadcast):
        client = _hermetic_client()
        try:
            resp = client.post(
                "/push/blocked",
                json={"container_id": "abc123", "file_path": "docs/gate.md", "question": "Ship it?"},
            )
        finally:
            client.__exit__(None, None, None)

    assert resp.json() == {"ok": True}
    assert state.WORKFLOWS["abc123"].state == WorkflowState.BLOCKED
    # The alert rides its own frame rather than a field on the snapshot, so it
    # fires on the block and not on every clock tick that re-pushes it.
    kinds = [m["type"] for m in captured]
    assert kinds.index("state") < kinds.index("notify")
    notify_frame = next(m for m in captured if m["type"] == "notify")
    assert notify_frame == {"type": "notify", "message": "coder-acme: Ship it?"}


def test_socket_blocked_delta_sends_the_same_notify_frame_as_the_http_push():
    _reset()
    wf = WorkflowContainer(
        container_id="abc123", name="coder-acme", state=WorkflowState.RUNNING, workspace_volume="v"
    )
    state.WORKFLOWS["abc123"] = wf

    captured: list[dict] = []

    async def _capture_broadcast(message):
        captured.append(message)

    with patch.object(state, "broadcast", _capture_broadcast):
        asyncio.run(
            groom_app._apply_socket_blocked(
                "abc123", {"file_path": "docs/gate.md", "question": "Ship it?"}
            )
        )

    assert state.WORKFLOWS["abc123"].state == WorkflowState.BLOCKED
    notify_frame = next(m for m in captured if m["type"] == "notify")
    assert notify_frame == {"type": "notify", "message": "coder-acme: Ship it?"}


def test_the_notify_message_truncates_the_question_to_the_limit():
    _reset()
    limit = groom_app._QUESTION_NOTIFY_LIMIT
    question = "q" * (limit + 50)
    wf = WorkflowContainer(
        container_id="abc123", name="w", state=WorkflowState.RUNNING, workspace_volume="v"
    )
    state.WORKFLOWS["abc123"] = wf

    captured: list[dict] = []

    async def _capture_broadcast(message):
        captured.append(message)

    with patch.object(state, "broadcast", _capture_broadcast):
        asyncio.run(
            groom_app._apply_socket_blocked("abc123", {"file_path": "g.md", "question": question})
        )

    # A toast is an interruption, not the pane: the whole question is already on
    # the wire in the run's detail payload.
    notify_frame = next(m for m in captured if m["type"] == "notify")
    assert notify_frame["message"] == "w: " + "q" * limit


# ---- run detail + its refreshable slices (the fleet list's click target) ----
def test_worker_detail_and_pushed_slices():
    _reset()
    wf = WorkflowContainer(
        container_id="abc123", name="w", state=WorkflowState.RUNNING,
        current_node="write_epic", run_id="run-1",
    )
    state.WORKFLOWS["abc123"] = wf

    client = _hermetic_client()
    try:
        detail = client.get("/worker/abc123")
        # Async now: its facts ride store reads that must run off the event loop.
        pushed = asyncio.run(groom_app._detail_message(wf))
    finally:
        client.__exit__(None, None, None)

    # The fetch and the push must deliver the *same* object, because the client
    # feeds both to one store slot: a pushed refresh that carried less than the
    # fetch would make the pane change every time it reconnected. It can carry the
    # whole pane — gates included — because the components are keyed, so the answer
    # textarea keeps its DOM node and a half-typed answer survives the re-render.
    assert detail.json() == pushed["detail"]
    assert pushed["type"] == "detail" and pushed["id"] == "abc123"
    assert pushed["detail"]["found"] is True
    assert pushed["detail"]["head"]["node"] == "write_epic"


def test_the_live_slice_endpoint_is_gone():
    # Phase 2 replaced a per-tab 5s poll with a subscription. Leaving the route
    # registered would let a stale cached page keep polling it forever, and the
    # push path would never be the only one exercised.
    _reset()
    client = _hermetic_client()
    try:
        assert client.get("/worker/abc123/live").status_code == 404
    finally:
        client.__exit__(None, None, None)


# ---- the per-tab subscription: who has which run open ----
def test_watch_registers_the_tab_and_pushes_that_run_immediately():
    # The immediate push is what makes a reconnect self-healing: the client re-sends
    # `watch` on every socket open and gets current slices back without a fetch.
    _reset()
    state.WORKFLOWS["abc123"] = WorkflowContainer(
        container_id="abc123", name="w", state=WorkflowState.RUNNING, run_id="run-1"
    )

    async def drive():
        queue = asyncio.Queue()
        state.add_client(queue)
        await groom_app._handle_command({"cmd": "watch", "run_id": "abc123"}, queue)
        return queue, queue.get_nowait()

    queue, first = asyncio.run(drive())
    assert state.WATCHING[queue] == "abc123"
    assert first["type"] == "detail" and first["id"] == "abc123"


def test_a_detail_push_reaches_only_the_tabs_watching_that_run():
    # The whole point of the registry. Broadcasting every open run's detail to every
    # tab costs bandwidth proportional to tabs × runs, and each tab discards nearly
    # all of it — which is what the old per-tab poll was avoiding by other means.
    _reset()
    for cid in ("abc123", "def456"):
        state.WORKFLOWS[cid] = WorkflowContainer(
            container_id=cid, name=cid, state=WorkflowState.RUNNING, run_id=cid
        )

    async def drive():
        watcher, other, idle = asyncio.Queue(), asyncio.Queue(), asyncio.Queue()
        for q in (watcher, other, idle):
            state.add_client(q)
        state.watch(watcher, "abc123")
        state.watch(other, "def456")
        await groom_app._push_detail("abc123")
        return watcher, other, idle

    watcher, other, idle = asyncio.run(drive())
    assert watcher.get_nowait()["id"] == "abc123"
    assert other.empty() and idle.empty()


def test_a_closed_tab_stops_being_a_watcher():
    # A subscription pointing at a queue nobody reads would grow WATCHING for the
    # life of the process, and _push_detail would render for an audience of nobody.
    _reset()
    queue = asyncio.Queue()
    state.add_client(queue)
    state.watch(queue, "abc123")
    state.remove_client(queue)
    assert state.watched_ids() == set()
    assert state.watchers_of("abc123") == []


def test_the_clock_refreshes_every_open_pane_alongside_the_fleet():
    # Same argument as the fleet list: "in node 12m" and the log trail are derived
    # from `now`, and a merely-running run emits no state change to push.
    _reset()
    state.WORKFLOWS["abc123"] = WorkflowContainer(
        container_id="abc123", name="w", state=WorkflowState.RUNNING, run_id="run-1"
    )

    async def drive():
        queue = asyncio.Queue()
        state.add_client(queue)
        state.watch(queue, "abc123")
        task = asyncio.create_task(groom_app._live_loop())
        try:
            seen = []
            while len(seen) < 2:
                seen.append(await asyncio.wait_for(queue.get(), timeout=2.0))
            return seen
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    with patch.object(groom_app, "LIVE_TICK_S", 0.01):
        seen = asyncio.run(drive())

    assert [m["type"] for m in seen] == ["state", "detail"]


def test_api_state_is_the_resync_payload():
    _reset()
    state.WORKFLOWS["abc123"] = WorkflowContainer(
        container_id="abc123", name="coder-001", state=WorkflowState.RUNNING
    )

    client = _hermetic_client()
    try:
        body = client.get("/api/state").json()
        filtered = client.get("/api/state", params={"q": "nomatch"}).json()
    finally:
        client.__exit__(None, None, None)

    assert body["type"] == "state"
    assert [r["id"] for r in body["runs"]] == ["abc123"]
    assert body["status"]["counts"]["running"] == 1
    assert filtered["runs"] == []


def test_api_state_and_the_socket_push_the_same_payload():
    # The point of the projection module: recovering from a dead socket is not a
    # second rendering path that can rot unobserved, because it is the same JSON.
    _reset()
    state.WORKFLOWS["abc123"] = WorkflowContainer(
        container_id="abc123", name="coder-001", state=WorkflowState.RUNNING
    )

    pushed = {}

    async def _capture(message):
        pushed["message"] = message

    client = _hermetic_client()
    try:
        body = client.get("/api/state").json()
        with patch.object(state, "broadcast", _capture):
            asyncio.run(groom_app._broadcast_shell())
    finally:
        client.__exit__(None, None, None)

    # `ts` is stamped per call, so compare everything the browser renders from.
    assert {k: v for k, v in pushed["message"].items() if k != "ts"} == {
        k: v for k, v in body.items() if k != "ts"
    }


# ---- the live clock: absence can't be pushed, so the list is re-rendered on a tick ----
def test_live_loop_repushes_the_run_list_to_connected_clients():
    # The row's liveness and its "silent 4m" / "in node 12m" are derived from
    # `now` at projection time. Every other broadcast is edge-triggered, and the event
    # that should turn a run's dot dead — it stopped emitting — is an absence, which
    # no ingest can deliver. Without this tick the row keeps asserting it is alive.
    _reset()
    state.WORKFLOWS["abc123"] = WorkflowContainer(
        container_id="abc123", name="coder-001", state=WorkflowState.RUNNING
    )

    async def drive():
        queue = asyncio.Queue()
        state.add_client(queue)
        task = asyncio.create_task(groom_app._live_loop())
        try:
            return await asyncio.wait_for(queue.get(), timeout=2.0)
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    with patch.object(groom_app, "LIVE_TICK_S", 0.01):
        pushed = asyncio.run(drive())

    assert pushed["type"] == "state"
    assert [r["id"] for r in pushed["runs"]] == ["abc123"]


def test_live_loop_skips_the_render_when_nobody_is_watching():
    # A tick with no client attached would render the whole fleet into a fan-out of
    # zero — pure cost on a machine left serving overnight.
    _reset()
    calls = []

    async def drive():
        task = asyncio.create_task(groom_app._live_loop())
        await asyncio.sleep(0.1)  # many ticks at the patched interval
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _spy():
        calls.append(1)

    with patch.object(groom_app, "LIVE_TICK_S", 0.01), \
         patch.object(groom_app, "_broadcast_shell", _spy):
        asyncio.run(drive())

    assert calls == []


def test_live_loop_survives_a_failing_tick():
    # The watch must not be the thing that stops: one bad render (or a dead client)
    # can't be allowed to kill the clock that reports everything else's death.
    _reset()
    calls = []

    async def _boom():
        calls.append(1)
        raise RuntimeError("render blew up")

    async def drive():
        state.add_client(asyncio.Queue())
        task = asyncio.create_task(groom_app._live_loop())
        await asyncio.sleep(0.1)
        alive = not task.done()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        return alive

    with patch.object(groom_app, "LIVE_TICK_S", 0.01), \
         patch.object(groom_app, "_broadcast_shell", _boom):
        still_running = asyncio.run(drive())

    assert still_running and len(calls) > 1  # kept ticking past the first failure


# ---- Files/Diff panels: container+repo picker and per-checkout reads ----
def test_repos_endpoint_lists_one_entry_per_container_repo():
    _reset()
    state.WORKFLOWS["abc123"] = WorkflowContainer(
        container_id="abc123", name="coder-001", workspace_volume="ws-vol", state=WorkflowState.RUNNING
    )
    state.WORKFLOWS["novol"] = WorkflowContainer(container_id="novol", name="pending")  # no volume → skipped

    client = _hermetic_client()
    try:
        with patch.object(groom_app.docker_io, "list_repo_dirs", return_value=["acme", "globex"]):
            resp = client.get("/repos")
    finally:
        client.__exit__(None, None, None)

    groups = resp.json()
    assert [g["container"] for g in groups] == ["abc123"]  # volume-less workflow contributes no group
    assert [r["label"] for r in groups[0]["repos"]] == ["coder-001/acme", "coder-001/globex"]


def test_repos_endpoint_reads_native_run_from_local_disk():
    # A native run shares groom's host, so its checkouts are enumerated from local
    # disk (localfs), never through a throwaway docker container.
    _reset()
    state.WORKFLOWS["nat1"] = WorkflowContainer(
        container_id="nat1", name="author-docs-app", native=True,
        workspace_volume="/host/checkout", state=WorkflowState.RUNNING,
    )

    client = _hermetic_client()
    try:
        with patch.object(groom_app.localfs, "list_repo_dirs", return_value=[""]) as ls, patch.object(
            groom_app.docker_io, "list_repo_dirs",
            side_effect=AssertionError("a native run must not touch docker"),
        ):
            resp = client.get("/repos")
    finally:
        client.__exit__(None, None, None)

    assert ls.call_args[0] == ("/host/checkout",)
    groups = resp.json()
    # a bare workspace-root entry (repo="") — the run is browsable even with no checkout under it
    assert [g["repos"] for g in groups] == [[{"repo": "", "label": "author-docs-app"}]]


def test_files_endpoint_returns_a_json_path_list():
    _reset()
    state.WORKFLOWS["abc123"] = WorkflowContainer(container_id="abc123", name="w", workspace_volume="ws-vol")

    client = _hermetic_client()
    try:
        with patch.object(groom_app.docker_io, "list_files", return_value=["README.md", "src/a.py"]) as lf:
            resp = client.get("/files/abc123", params={"repo": "acme"})
    finally:
        client.__exit__(None, None, None)

    assert resp.json() == {"paths": ["README.md", "src/a.py"]}
    assert lf.call_args[0] == ("ws-vol", "acme")


def test_file_endpoint_joins_repo_and_path_and_returns_content():
    _reset()
    state.WORKFLOWS["abc123"] = WorkflowContainer(container_id="abc123", name="w", workspace_volume="ws-vol")

    client = _hermetic_client()
    try:
        with patch.object(groom_app.docker_io, "read_file", return_value="print(1)\n") as rf:
            resp = client.get("/file/abc123", params={"repo": "acme", "path": "src/a.py"})
    finally:
        client.__exit__(None, None, None)

    # `lang` is projected server-side so the extension table lives in one place.
    assert resp.json() == {"path": "src/a.py", "content": "print(1)\n", "lang": "python"}
    assert rf.call_args[0] == ("ws-vol", "acme/src/a.py")


def test_file_endpoint_swallows_unsafe_path():
    _reset()
    state.WORKFLOWS["abc123"] = WorkflowContainer(container_id="abc123", name="w", workspace_volume="ws-vol")

    client = _hermetic_client()
    try:
        # read_file raises ValueError on a traversal path; the handler must not 500.
        with patch.object(groom_app.docker_io, "read_file", side_effect=ValueError("unsafe")):
            resp = client.get("/file/abc123", params={"repo": "acme", "path": "../../etc/passwd"})
    finally:
        client.__exit__(None, None, None)

    assert resp.status_code == 200
    assert resp.json()["content"] == ""


def test_file_endpoint_reads_a_native_runs_workspace_by_gate_path(tmp_path):
    # The dashboard's gate disclosure asks for `/file/<run>?path=<gate.file_path>` with
    # no repo: a native gate's path is already relative to the run's workspace, and
    # that workspace is the volume `/file/` reads from.
    _reset()
    gate = tmp_path / "docs" / "context.md"
    gate.parent.mkdir(parents=True)
    gate.write_text("STATUS: AWAITING_OPERATOR\n\n## Findings\n\n- one\n")
    state.WORKFLOWS["run-9"] = WorkflowContainer(
        container_id="run-9", name="w", run_id="run-9", native=True, workspace_volume=str(tmp_path)
    )

    client = _hermetic_client()
    try:
        resp = client.get("/file/run-9", params={"path": "docs/context.md"})
    finally:
        client.__exit__(None, None, None)

    assert resp.json() == {"path": "docs/context.md", "content": gate.read_text(), "lang": "markdown"}


def test_diff_endpoint_passes_repo_through():
    _reset()
    state.WORKFLOWS["abc123"] = WorkflowContainer(container_id="abc123", name="w", workspace_volume="ws-vol")

    client = _hermetic_client()
    try:
        with patch.object(groom_app.docker_io, "git_diff", return_value="diff --git a/x b/x\n") as gd:
            resp = client.get("/diff/abc123", params={"repo": "acme"})
    finally:
        client.__exit__(None, None, None)

    assert resp.json() == {"diff": "diff --git a/x b/x\n"}
    assert gd.call_args[0] == ("ws-vol", "acme")


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
def test_handle_answer_flips_state_and_broadcasts_an_answered_event():
    _reset()
    wf = WorkflowContainer(container_id="abc123", name="w", state=WorkflowState.BLOCKED, workspace_volume="v")
    wf.gates["docs/gate.md"] = GateInfo(workflow_id="abc123", file_path="docs/gate.md", question="Q?")
    state.WORKFLOWS["abc123"] = wf

    captured = {}

    async def _fake_answer_gate(
        cid, fp, ans, *, workspace_volume, native=False, allow_headerless=False
    ):
        state.clear_gate(cid, fp)  # mirror the real clear
        return AnswerResult(ok=True, message="answered")

    async def _capture_broadcast(message):
        captured.setdefault("messages", []).append(message)

    with patch.object(groom_app, "answer_gate", _fake_answer_gate), \
         patch.object(state, "broadcast", _capture_broadcast):
        asyncio.run(
            groom_app._handle_command(
                {"cmd": "answer", "workflow_id": "abc123", "file_path": "docs/gate.md", "answer": "yes"}
            )
        )

    assert state.WORKFLOWS["abc123"].state == WorkflowState.RUNNING
    # The fleet changed shape (a gate closed) *and* this particular gate was
    # answered: the first is fleet-wide, the second is what lets a tab decide
    # whether the answered run is the one it has open.
    kinds = [m["type"] for m in captured["messages"]]
    assert "state" in kinds
    answered = next(m for m in captured["messages"] if m["type"] == "answered")
    assert answered["id"] == "abc123" and answered["file_path"] == "docs/gate.md"


def test_handle_answer_failure_does_not_flip_or_dispatch():
    _reset()
    wf = WorkflowContainer(container_id="abc123", name="w", state=WorkflowState.BLOCKED, workspace_volume="v")
    wf.gates["docs/gate.md"] = GateInfo(workflow_id="abc123", file_path="docs/gate.md", question="Q?")
    state.WORKFLOWS["abc123"] = wf

    captured = {}

    async def _fake_answer_gate(
        cid, fp, ans, *, workspace_volume, native=False, allow_headerless=False
    ):
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


# ---- /api/run/{run_id}/outbox: addressed by run id, not container id ----
def test_outbox_get_names_the_gate_the_run_is_parked_on():
    _reset()
    wf = WorkflowContainer(container_id="abc123", name="w", run_id="run-9", workspace_volume="v")
    wf.gates["docs/gate.md"] = GateInfo(workflow_id="abc123", file_path="docs/gate.md", question="Ship it?")
    state.WORKFLOWS["abc123"] = wf

    client = _hermetic_client()
    try:
        resp = client.get("/api/run/run-9/outbox")
    finally:
        client.__exit__(None, None, None)

    assert resp.json() == {
        "found": True,
        "file_path": "docs/gate.md",
        "question": "Ship it?",
        "status": "AWAITING_OPERATOR",
    }


def test_outbox_get_on_a_native_run_is_keyed_by_run_id_directly():
    _reset()
    wf = WorkflowContainer(container_id="run-9", name="w", run_id="run-9", native=True, workspace_volume="/host/ws")
    wf.gates["docs/gate.md"] = GateInfo(workflow_id="run-9", file_path="docs/gate.md", question="Ship it?")
    state.WORKFLOWS["run-9"] = wf

    client = _hermetic_client()
    try:
        resp = client.get("/api/run/run-9/outbox")
    finally:
        client.__exit__(None, None, None)

    assert resp.json()["found"] is True
    assert resp.json()["file_path"] == "docs/gate.md"


def test_outbox_get_with_no_live_gate_is_not_found():
    _reset()
    wf = WorkflowContainer(container_id="abc123", name="w", run_id="run-9", workspace_volume="v")
    state.WORKFLOWS["abc123"] = wf

    client = _hermetic_client()
    try:
        resp = client.get("/api/run/run-9/outbox")
    finally:
        client.__exit__(None, None, None)

    assert resp.json() == {"found": False}


def test_outbox_get_for_an_unknown_run_id_is_not_found():
    _reset()

    client = _hermetic_client()
    try:
        resp = client.get("/api/run/no-such-run/outbox")
    finally:
        client.__exit__(None, None, None)

    assert resp.json() == {"found": False}


def test_outbox_post_resolves_run_id_to_container_id_before_answering():
    _reset()
    wf = WorkflowContainer(container_id="abc123", name="w", run_id="run-9", state=WorkflowState.BLOCKED, workspace_volume="v")
    wf.gates["docs/gate.md"] = GateInfo(workflow_id="abc123", file_path="docs/gate.md", question="Ship it?")
    state.WORKFLOWS["abc123"] = wf

    captured = {}

    async def _fake_answer_gate(cid, fp, ans, *, workspace_volume, native=False, allow_headerless=False):
        captured["container_id"] = cid
        captured["answer"] = ans
        state.clear_gate(cid, fp)
        return AnswerResult(ok=True, message="answered")

    with patch.object(groom_app, "answer_gate", _fake_answer_gate):
        client = _hermetic_client()
        try:
            resp = client.post(
                "/api/run/run-9/outbox", json={"file_path": "docs/gate.md", "answer": "go ahead"}
            )
        finally:
            client.__exit__(None, None, None)

    assert resp.json() == {"ok": True, "message": "answered"}
    assert captured == {"container_id": "abc123", "answer": "go ahead"}
    assert state.WORKFLOWS["abc123"].state == WorkflowState.RUNNING


def test_outbox_post_race_returns_the_already_answered_message_and_does_not_flip_state():
    _reset()
    wf = WorkflowContainer(container_id="abc123", name="w", run_id="run-9", state=WorkflowState.BLOCKED, workspace_volume="v")
    wf.gates["docs/gate.md"] = GateInfo(workflow_id="abc123", file_path="docs/gate.md", question="Ship it?")
    state.WORKFLOWS["abc123"] = wf

    async def _fake_answer_gate(cid, fp, ans, *, workspace_volume, native=False, allow_headerless=False):
        return AnswerResult(ok=False, message="already answered in another tab")

    with patch.object(groom_app, "answer_gate", _fake_answer_gate):
        client = _hermetic_client()
        try:
            resp = client.post(
                "/api/run/run-9/outbox", json={"file_path": "docs/gate.md", "answer": "go ahead"}
            )
        finally:
            client.__exit__(None, None, None)

    assert resp.json() == {"ok": False, "message": "already answered in another tab"}
    assert state.WORKFLOWS["abc123"].state == WorkflowState.BLOCKED


def test_outbox_post_for_an_unknown_run_id_is_an_error_not_a_500():
    _reset()

    client = _hermetic_client()
    try:
        resp = client.post(
            "/api/run/no-such-run/outbox", json={"file_path": "docs/gate.md", "answer": "go ahead"}
        )
    finally:
        client.__exit__(None, None, None)

    assert resp.json() == {"ok": False, "message": "no such run"}


def test_inbox_get_on_a_native_run_reads_outstanding_messages_by_default(tmp_path):
    _reset()
    run_dir = tmp_path / "run-9"
    run_dir.mkdir()
    inbox.append(run_dir / "inbox.jsonl", id="m1", body="hold off", at="t0")
    inbox.append(run_dir / "inbox.jsonl", id="m2", body="go ahead", at="t1")
    inbox.reply(run_dir / "inbox.jsonl", "m2", "done", at="t2")
    wf = WorkflowContainer(container_id="run-9", name="w", run_id="run-9", native=True, runs_volume=str(run_dir))
    state.WORKFLOWS["run-9"] = wf

    client = _hermetic_client()
    try:
        resp = client.get("/api/run/run-9/inbox")
    finally:
        client.__exit__(None, None, None)

    ids = [m["id"] for m in resp.json()["messages"]]
    assert ids == ["m1"]


def test_inbox_get_include_all_returns_replied_messages_too(tmp_path):
    _reset()
    run_dir = tmp_path / "run-9"
    run_dir.mkdir()
    inbox.append(run_dir / "inbox.jsonl", id="m1", body="go ahead", at="t0")
    inbox.reply(run_dir / "inbox.jsonl", "m1", "done", at="t1")
    wf = WorkflowContainer(container_id="run-9", name="w", run_id="run-9", native=True, runs_volume=str(run_dir))
    state.WORKFLOWS["run-9"] = wf

    client = _hermetic_client()
    try:
        resp = client.get("/api/run/run-9/inbox", params={"include_all": "true"})
    finally:
        client.__exit__(None, None, None)

    messages = resp.json()["messages"]
    assert len(messages) == 1
    assert messages[0]["reply"] == "done"


def test_inbox_get_for_an_unknown_run_id_is_empty_not_an_error():
    _reset()

    client = _hermetic_client()
    try:
        resp = client.get("/api/run/no-such-run/inbox")
    finally:
        client.__exit__(None, None, None)

    assert resp.json() == {"messages": []}


def test_inbox_post_on_a_native_run_appends_and_is_read_back(tmp_path):
    _reset()
    run_dir = tmp_path / "run-9"
    run_dir.mkdir()
    wf = WorkflowContainer(container_id="run-9", name="w", run_id="run-9", native=True, runs_volume=str(run_dir))
    state.WORKFLOWS["run-9"] = wf

    client = _hermetic_client()
    try:
        resp = client.post("/api/run/run-9/inbox", json={"body": "hold off on the migration"})
    finally:
        client.__exit__(None, None, None)

    assert resp.json()["ok"] is True
    assert resp.json()["message"]["body"] == "hold off on the migration"
    stored = inbox.all_messages(run_dir / "inbox.jsonl")
    assert len(stored) == 1
    assert stored[0].body == "hold off on the migration"


def test_inbox_post_with_no_body_is_an_error(tmp_path):
    _reset()
    wf = WorkflowContainer(container_id="run-9", name="w", run_id="run-9", native=True, runs_volume=str(tmp_path))
    state.WORKFLOWS["run-9"] = wf

    client = _hermetic_client()
    try:
        resp = client.post("/api/run/run-9/inbox", json={"body": ""})
    finally:
        client.__exit__(None, None, None)

    assert resp.json() == {"ok": False, "message": "message body is required"}


def test_inbox_post_for_an_unknown_run_id_is_an_error_not_a_500():
    _reset()

    client = _hermetic_client()
    try:
        resp = client.post("/api/run/no-such-run/inbox", json={"body": "go ahead"})
    finally:
        client.__exit__(None, None, None)

    assert resp.json() == {"ok": False, "message": "no such run"}


def test_inbox_get_on_a_docker_backed_run_reads_through_docker_io():
    _reset()
    wf = WorkflowContainer(container_id="abc123", name="w", run_id="run-9", runs_volume="runs-vol")
    state.WORKFLOWS["abc123"] = wf

    with (
        patch.object(groom_app.docker_io, "list_run_dirs", return_value=["demo-20260101-000000"]),
        patch.object(
            groom_app.docker_io,
            "read_file",
            return_value='{"id": "m1", "body": "go ahead", "at": "t0", "reply": "", "replied_at": ""}\n',
        ),
    ):
        client = _hermetic_client()
        try:
            resp = client.get("/api/run/run-9/inbox")
        finally:
            client.__exit__(None, None, None)

    assert [m["id"] for m in resp.json()["messages"]] == ["m1"]


def test_inbox_post_on_a_docker_backed_run_writes_through_docker_io():
    _reset()
    wf = WorkflowContainer(container_id="abc123", name="w", run_id="run-9", runs_volume="runs-vol")
    state.WORKFLOWS["abc123"] = wf
    written = {}

    def _fake_write_file(volume, rel_path, content):
        written["volume"] = volume
        written["rel_path"] = rel_path
        written["content"] = content
        return True

    with (
        patch.object(groom_app.docker_io, "list_run_dirs", return_value=["demo-20260101-000000"]),
        patch.object(groom_app.docker_io, "read_file", return_value=""),
        patch.object(groom_app.docker_io, "write_file", _fake_write_file),
    ):
        client = _hermetic_client()
        try:
            resp = client.post("/api/run/run-9/inbox", json={"body": "go ahead"})
        finally:
            client.__exit__(None, None, None)

    assert resp.json()["ok"] is True
    assert written["volume"] == "runs-vol"
    assert written["rel_path"] == "demo-20260101-000000/inbox.jsonl"
    assert "go ahead" in written["content"]


def test_inbox_post_on_a_docker_run_with_no_run_dir_yet_is_an_error():
    _reset()
    wf = WorkflowContainer(container_id="abc123", name="w", run_id="run-9", runs_volume="runs-vol")
    state.WORKFLOWS["abc123"] = wf

    with patch.object(groom_app.docker_io, "list_run_dirs", return_value=[]):
        client = _hermetic_client()
        try:
            resp = client.post("/api/run/run-9/inbox", json={"body": "go ahead"})
        finally:
            client.__exit__(None, None, None)

    assert resp.json() == {"ok": False, "message": "no run directory yet"}


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
            # The task the spawn just created — `_scan_task` is None only before the
            # first spawn, which this scenario is past.
            scan_task = groom_app._scan_task
            assert scan_task is not None
            await scan_task  # let the background task finish

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


# ---- Data plane prefers the live sidecar socket, falls back to volume reads ----
def test_files_prefers_sidecar_socket_when_connected():
    _reset()
    state.WORKFLOWS["abc123"] = WorkflowContainer(container_id="abc123", name="w", workspace_volume="ws-vol")
    sidecar_hub.CONNECTIONS["abc123"] = _FakeConn("abc123", result={"paths": ["a.py", "b.py"]})

    client = _hermetic_client()
    try:
        with patch.object(groom_app.docker_io, "list_files") as lf:
            resp = client.get("/files/abc123", params={"repo": "acme"})
    finally:
        client.__exit__(None, None, None)

    assert resp.json() == {"paths": ["a.py", "b.py"]}
    lf.assert_not_called()  # socket served it; no throwaway container


def test_files_falls_back_to_volume_when_socket_errors():
    _reset()
    state.WORKFLOWS["abc123"] = WorkflowContainer(container_id="abc123", name="w", workspace_volume="ws-vol")
    sidecar_hub.CONNECTIONS["abc123"] = _FakeConn("abc123", error=True)

    client = _hermetic_client()
    try:
        with patch.object(groom_app.docker_io, "list_files", return_value=["README.md"]) as lf:
            resp = client.get("/files/abc123", params={"repo": "acme"})
    finally:
        client.__exit__(None, None, None)

    assert resp.json() == {"paths": ["README.md"]}
    assert lf.call_args[0] == ("ws-vol", "acme")


def test_file_content_prefers_sidecar_socket():
    _reset()
    state.WORKFLOWS["abc123"] = WorkflowContainer(container_id="abc123", name="w", workspace_volume="ws-vol")
    sidecar_hub.CONNECTIONS["abc123"] = _FakeConn("abc123", result={"content": "print(1)\n"})

    client = _hermetic_client()
    try:
        with patch.object(groom_app.docker_io, "read_file") as rf:
            resp = client.get("/file/abc123", params={"repo": "acme", "path": "a.py"})
    finally:
        client.__exit__(None, None, None)

    assert resp.json()["content"] == "print(1)\n"
    rf.assert_not_called()


def test_diff_prefers_sidecar_socket():
    _reset()
    state.WORKFLOWS["abc123"] = WorkflowContainer(container_id="abc123", name="w", workspace_volume="ws-vol")
    sidecar_hub.CONNECTIONS["abc123"] = _FakeConn("abc123", result={"diff": "diff --git a/x b/x\n"})

    client = _hermetic_client()
    try:
        with patch.object(groom_app.docker_io, "git_diff") as gd:
            resp = client.get("/diff/abc123", params={"repo": "acme"})
    finally:
        client.__exit__(None, None, None)

    assert resp.json() == {"diff": "diff --git a/x b/x\n"}
    gd.assert_not_called()


# ---- /reload broadcasts to connected sidecars ----
def test_reload_broadcasts_to_all_connected_sidecars():
    _reset()
    c1, c2 = _FakeConn("a"), _FakeConn("b")
    sidecar_hub.CONNECTIONS["a"] = c1
    sidecar_hub.CONNECTIONS["b"] = c2

    client = _hermetic_client()
    try:
        resp = client.post("/reload")
    finally:
        client.__exit__(None, None, None)

    assert resp.json() == {"ok": True, "reloaded": 2}
    assert c1.reloaded and c2.reloaded


def test_reload_targets_one_container_when_id_given():
    _reset()
    c1, c2 = _FakeConn("a"), _FakeConn("b")
    sidecar_hub.CONNECTIONS["a"] = c1
    sidecar_hub.CONNECTIONS["b"] = c2

    client = _hermetic_client()
    try:
        resp = client.post("/reload", params={"container_id": "a"})
    finally:
        client.__exit__(None, None, None)

    assert resp.json()["reloaded"] == 1
    assert c1.reloaded and not c2.reloaded


# ---- hello advertise folds a connected container's full state into the fleet ----
def _run_apply_hello(container_id: str, data: dict) -> None:
    async def _noop_ensure(cid: str) -> None:  # skip docker inspect
        pass

    async def _noop_broadcast(fragment) -> None:
        pass

    async def _scenario() -> None:
        with patch.object(groom_app, "_ensure_volumes", _noop_ensure), \
             patch.object(state, "broadcast", _noop_broadcast):
            await groom_app._apply_hello(container_id, data)

    asyncio.run(_scenario())


def test_apply_hello_marks_blocked_with_gate():
    _reset()
    _run_apply_hello(
        "abc123def456",
        {
            "identity": {"container_id": "abc123def456", "name": "coder-1", "repo_name": "Acme", "repo_branch": "main"},
            "snapshot": {"current_node": "await_operator", "terminal": "", "gates": [{"file_path": "docs/gate.md", "question": "Which?"}]},
        },
    )
    wf = state.WORKFLOWS["abc123def456"]
    assert wf.state == WorkflowState.BLOCKED
    assert wf.current_node == "await_operator"
    assert wf.repo_name == "Acme"
    assert "docs/gate.md" in wf.gates


def test_apply_hello_running_when_no_gates():
    _reset()
    _run_apply_hello(
        "abc123def456",
        {"identity": {"container_id": "abc123def456", "name": "coder-1"}, "snapshot": {"current_node": "build", "terminal": "", "gates": []}},
    )
    assert state.WORKFLOWS["abc123def456"].state == WorkflowState.RUNNING


def test_apply_hello_finished_when_terminal():
    _reset()
    _run_apply_hello(
        "abc123def456",
        {"identity": {"container_id": "abc123def456", "name": "coder-1"}, "snapshot": {"current_node": "done", "terminal": "done", "gates": []}},
    )
    assert state.WORKFLOWS["abc123def456"].state == WorkflowState.FINISHED


def test_apply_hello_reconnect_rebuilds_gates_authoritatively():
    _reset()
    # A stale gate lingers from a previous session; the fresh hello has none.
    wf = WorkflowContainer(container_id="abc123def456", name="w", state=WorkflowState.BLOCKED)
    wf.gates["docs/old.md"] = GateInfo(workflow_id="abc123def456", file_path="docs/old.md", question="stale?")
    state.WORKFLOWS["abc123def456"] = wf

    _run_apply_hello(
        "abc123def456",
        {"identity": {"container_id": "abc123def456"}, "snapshot": {"current_node": "build", "terminal": "", "gates": []}},
    )
    # Re-advertise is authoritative: the stale gate is gone and the worker is running again.
    assert state.WORKFLOWS["abc123def456"].gates == {}
    assert state.WORKFLOWS["abc123def456"].state == WorkflowState.RUNNING


def test_the_shell_stamps_every_asset_url_with_the_files_version():
    """An unstamped ``/assets/dashboard.js`` is a URL a browser may reuse from
    cache without asking, so a client change can land while a tab keeps running
    the old bundle against the new payload — silently.
    """
    html = groom_app.stamp_assets(
        b'<link rel="stylesheet" href="/assets/dashboard.css">'
        b'<script type="module" src="/assets/dashboard.js"></script>'
    )
    js = (groom_app.ASSETS_DIR / "dashboard.js").stat()
    assert f'src="/assets/dashboard.js?v={int(js.st_mtime)}-{js.st_size}"'.encode() in html
    assert b'href="/assets/dashboard.css?v=' in html


def test_an_asset_that_is_not_on_disk_keeps_its_url():
    """Stamping is an optimization of the cache story, not a routing decision: a
    missing file still 404s at its own URL rather than at a mangled one.
    """
    html = b'<script src="/assets/nope.js"></script>'
    assert groom_app.stamp_assets(html) == html


def test_the_served_shell_is_the_stamped_one():
    with TestClient(app=groom_app.create_app()) as client:
        body = client.get("/").content
    assert b'src="/assets/dashboard.js?v=' in body


# --------------------------------------------------------------------------- #
# Operator gates over the run's control socket: the socket-first answer path
# and the questions poll that reconciles rows from the run's own listing.
# --------------------------------------------------------------------------- #
class _GateConn(_FakeConn):
    """A `_FakeConn` whose replies differ per RPC method — the answer flow asks
    `getQuestions` before `answerGate`, and one canned result can't play both."""

    def __init__(self, container_id: str, by_method: dict) -> None:
        super().__init__(container_id)
        self.by_method = by_method
        self.calls: list = []

    async def rpc(self, method: str, params: dict, *, timeout: float = 0.0):
        self.calls.append((method, params))
        result = self.by_method[method]
        if isinstance(result, Exception):
            raise result
        return result


_LISTING = {
    "ok": True,
    "questions": [
        {
            "path": "/workspace/docs/gate.md",
            "question": "STATUS: AWAITING_OPERATOR\n\n## Questions from the agent\n\nShip it?\n",
            "kind": "operator",
            "since": "t0",
        }
    ],
}


def test_answer_goes_over_the_socket_first_and_uses_the_runs_own_path():
    _reset()
    wf = WorkflowContainer(container_id="abc123", name="w", state=WorkflowState.BLOCKED, workspace_volume="v")
    wf.gates["docs/gate.md"] = GateInfo(workflow_id="abc123", file_path="docs/gate.md", question="Ship it?")
    state.WORKFLOWS["abc123"] = wf
    conn = _GateConn("abc123", {
        "getQuestions": _LISTING,
        "answerGate": {"ok": True, "path": "/workspace/docs/gate.md"},
    })
    sidecar_hub.CONNECTIONS["abc123"] = conn

    async def _file_write_must_not_run(*args, **kwargs):
        raise AssertionError("the file fallback ran on a socket-acknowledged answer")

    with patch.object(groom_app, "answer_gate", _file_write_must_not_run):
        result = asyncio.run(groom_app._answer(wf, "abc123", "docs/gate.md", "go ahead"))

    assert result.ok is True
    # Ask-first: the answer carried the path exactly as the run spelled it.
    answered = next(p for m, p in conn.calls if m == "answerGate")
    assert answered["path"] == "/workspace/docs/gate.md"
    assert answered["body"] == "go ahead"
    # The run persisted the answer itself; groom just settles its row.
    assert wf.gates == {}
    assert wf.state == WorkflowState.RUNNING


def test_an_already_answered_refusal_is_terminal_with_no_file_fallback():
    _reset()
    wf = WorkflowContainer(container_id="abc123", name="w", state=WorkflowState.BLOCKED, workspace_volume="v")
    wf.gates["docs/gate.md"] = GateInfo(workflow_id="abc123", file_path="docs/gate.md", question="Ship it?")
    state.WORKFLOWS["abc123"] = wf
    sidecar_hub.CONNECTIONS["abc123"] = _GateConn("abc123", {
        "getQuestions": _LISTING,
        "answerGate": {"ok": False, "error": "already answered"},
    })

    async def _file_write_must_not_run(*args, **kwargs):
        raise AssertionError("the file fallback would double-write an answered gate")

    with patch.object(groom_app, "answer_gate", _file_write_must_not_run):
        result = asyncio.run(groom_app._answer(wf, "abc123", "docs/gate.md", "go ahead"))

    assert result.ok is False
    assert result.message == "already answered"


def test_a_gate_the_run_is_not_waiting_on_falls_back_to_the_file_write():
    _reset()
    wf = WorkflowContainer(container_id="abc123", name="w", state=WorkflowState.BLOCKED, workspace_volume="v")
    wf.gates["docs/other.md"] = GateInfo(workflow_id="abc123", file_path="docs/other.md", question="Q?")
    state.WORKFLOWS["abc123"] = wf
    # The run lists a different gate than the row being answered.
    sidecar_hub.CONNECTIONS["abc123"] = _GateConn("abc123", {"getQuestions": _LISTING})

    called = {}

    async def _fake_answer_gate(cid, fp, ans, *, workspace_volume, native=False, allow_headerless=False):
        called["file_path"] = fp
        return AnswerResult(ok=True, message="answered")

    with patch.object(groom_app, "answer_gate", _fake_answer_gate):
        result = asyncio.run(groom_app._answer(wf, "abc123", "docs/other.md", "go"))

    assert result.ok is True
    assert called["file_path"] == "docs/other.md"


def test_a_dead_socket_falls_back_to_the_file_write():
    _reset()
    wf = WorkflowContainer(container_id="abc123", name="w", state=WorkflowState.BLOCKED, workspace_volume="v")
    wf.gates["docs/gate.md"] = GateInfo(workflow_id="abc123", file_path="docs/gate.md", question="Q?")
    state.WORKFLOWS["abc123"] = wf  # no sidecar registered at all

    called = {}

    async def _fake_answer_gate(cid, fp, ans, *, workspace_volume, native=False, allow_headerless=False):
        called["file_path"] = fp
        return AnswerResult(ok=True, message="answered")

    with patch.object(groom_app, "answer_gate", _fake_answer_gate):
        result = asyncio.run(groom_app._answer(wf, "abc123", "docs/gate.md", "go"))

    assert result.ok is True
    assert called["file_path"] == "docs/gate.md"


def test_the_questions_poll_blocks_a_running_container_row():
    _reset()
    wf = WorkflowContainer(container_id="abc123", name="w", state=WorkflowState.RUNNING, workspace_volume="v")
    state.WORKFLOWS["abc123"] = wf
    sidecar_hub.CONNECTIONS["abc123"] = _GateConn("abc123", {"getQuestions": _LISTING})

    notified: list = []

    async def _capture_notify(message):
        notified.append(message)

    with patch.object(groom_app, "_broadcast_notify", _capture_notify):
        asyncio.run(groom_app._poll_gates_of("abc123"))

    assert wf.state == WorkflowState.BLOCKED
    # Keyed workspace-relative, like the sidecar's own gate rows; the question
    # is the extracted section, not the raw file dump.
    assert list(wf.gates) == ["docs/gate.md"]
    assert wf.gates["docs/gate.md"].question == "Ship it?"
    assert notified and "Ship it?" in notified[0]


def test_the_questions_poll_clears_a_row_whose_run_answered():
    _reset()
    wf = WorkflowContainer(container_id="abc123", name="w", state=WorkflowState.BLOCKED, workspace_volume="v")
    wf.gates["docs/gate.md"] = GateInfo(workflow_id="abc123", file_path="docs/gate.md", question="Q?")
    state.WORKFLOWS["abc123"] = wf
    sidecar_hub.CONNECTIONS["abc123"] = _GateConn(
        "abc123", {"getQuestions": {"ok": True, "questions": []}}
    )

    asyncio.run(groom_app._poll_gates_of("abc123"))

    assert wf.gates == {}
    assert wf.state == WorkflowState.RUNNING


def test_a_socket_miss_leaves_the_row_exactly_as_the_pushes_built_it():
    _reset()
    wf = WorkflowContainer(container_id="abc123", name="w", state=WorkflowState.BLOCKED, workspace_volume="v")
    wf.gates["docs/gate.md"] = GateInfo(workflow_id="abc123", file_path="docs/gate.md", question="Q?")
    state.WORKFLOWS["abc123"] = wf
    sidecar_hub.CONNECTIONS["abc123"] = _FakeConn("abc123", error=True)

    asyncio.run(groom_app._poll_gates_of("abc123"))

    assert list(wf.gates) == ["docs/gate.md"]
    assert wf.state == WorkflowState.BLOCKED


def test_push_blocked_schedules_an_immediate_reconciling_poll():
    _reset()
    state.WORKFLOWS["abc123"] = WorkflowContainer(container_id="abc123", name="w", workspace_volume="v")
    polled: list = []

    with patch.object(groom_app, "_poll_gate_soon", polled.append):
        client = _hermetic_client()
        try:
            resp = client.post(
                "/push/blocked",
                json={"container_id": "abc123", "file_path": "docs/gate.md", "question": "Q?"},
            )
        finally:
            client.__exit__(None, None, None)

    assert resp.json() == {"ok": True}
    assert polled == ["abc123"]


def test_native_gate_paths_resolve_like_the_checkpoint_arm(tmp_path):
    """The poll's native projection must key a gate exactly the way
    `_native_gate` does, or the two arms would double-list one gate."""
    _reset()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    wf = WorkflowContainer(
        container_id="run-9", name="w", run_id="run-9", native=True,
        workspace_volume=str(workspace),
    )
    inside = groom_app._gate_from_question(
        wf, {"path": str(workspace / "docs" / "gate.md"), "question": "## Questions\n\nGo?\n"}
    )
    assert inside is not None
    assert (inside.file_path, inside.base) == ("docs/gate.md", "")

    outside = groom_app._gate_from_question(
        wf, {"path": "/elsewhere/gate.md", "question": "Go?"}
    )
    assert outside is not None
    # Outside the exported workspace → anchored at the filesystem root, like
    # the checkpoint arm's fallback.
    assert (outside.file_path, outside.base) == ("elsewhere/gate.md", "/")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            # `make test` runs this file as a script, so pytest's fixtures are not
            # there to be injected. `tmp_path` is the only one the suite asks for,
            # and standing it up here is what keeps the two ways of running this
            # file — `python tests/test_app.py` and `pytest` — reporting the same
            # result instead of the script runner erroring on the signature.
            if "tmp_path" in inspect.signature(fn).parameters:
                with tempfile.TemporaryDirectory() as tmp:
                    fn(tmp_path=Path(tmp))
            else:
                fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
