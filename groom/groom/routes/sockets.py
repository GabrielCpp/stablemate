from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Annotated

from litestar import websocket
from litestar.connection import WebSocket
from litestar.exceptions import (
    WebSocketDisconnect,
)
from litestar.params import QueryParameter

from groom import (
    alerting,
    digest,
    live,
    native,
    projection,
    sidecar_hub,
    sidecar_turns,
    state,
)
from groom.alerting import _FEED_QUEUE_MAX, _QUESTION_NOTIFY_LIMIT
from groom.attention import (
    DigestFrame,
    EventFrame,
)
from groom.models import (
    GateInfo,
    WorkflowState,
)
from groom.native import _TAIL_RUNS, _all_workflows, _schedule_tail
from groom.native_attend import _attend_gates
from groom.routes.gates import _handle_command

logger = logging.getLogger(__name__)


async def _send_loop(socket: WebSocket, queue: asyncio.Queue) -> None:
    while True:
        message = await queue.get()
        await socket.send_text(json.dumps(message))


async def _recv_loop(socket: WebSocket, queue: asyncio.Queue) -> None:
    while True:
        data = await socket.receive_json()
        await _handle_command(data, queue)


@websocket("/ws")
async def dashboard_ws(socket: WebSocket) -> None:
    """One socket per open tab, carrying JSON in both directions: fleet-wide ``state``/``notify``/``answered`` frames plus this tab's own ``detail`` and ``answer_rejected`` frames down, ``{"cmd": "answer"|"watch", ...}`` up."""
    await socket.accept()
    queue = state.new_client_queue()
    state.add_client(queue)
    try:
        await socket.send_text(json.dumps(live.snapshot()))
        send_task = asyncio.create_task(_send_loop(socket, queue))
        recv_task = asyncio.create_task(_recv_loop(socket, queue))
        done, pending = await asyncio.wait({send_task, recv_task}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            exc = task.exception()
            if exc is not None and not isinstance(exc, WebSocketDisconnect):
                raise exc
    finally:
        state.remove_client(queue)


FEED_MIN_EVERY_S = 60.0


FEED_DEFAULT_EVERY_S = 1800.0


async def _until_disconnect(socket: WebSocket) -> None:
    """Return when the peer goes away; a feed client sends nothing, so anything it does send is dropped."""
    try:
        while True:
            await socket.receive_data("text")
    except WebSocketDisconnect:
        return


@websocket("/feed")
async def feed_ws(
    socket: WebSocket,
    run: Annotated[str, QueryParameter()],
    every: Annotated[float, QueryParameter()] = FEED_DEFAULT_EVERY_S,
    since: Annotated[float | None, QueryParameter()] = None,
) -> None:
    """One filtered socket for one run, meant for a program rather than a tab: ``event`` frames the moment an alert fires and a ``digest`` frame every ``every`` seconds, quiet or not, so silence reads as a signal."""
    await socket.accept()
    interval = max(every, FEED_MIN_EVERY_S)
    queue: asyncio.Queue = asyncio.Queue(maxsize=_FEED_QUEUE_MAX)
    state.add_feed(queue, run)
    seq = 0

    async def emit(frame: EventFrame | DigestFrame) -> None:
        await socket.send_text(frame.model_dump_json())

    try:
        now = time.time()
        if since is not None:
            replay = [(ts, event) for ts, event in state.EVENTS.get(run, ()) if ts > since]
            replayed = {event.event for _, event in replay}
            replay += [
                (now, event)
                for event in projection.attention_events(_all_workflows())
                if event.run_id == run and event.event not in replayed
            ]
            window_start = since
        else:
            replay = [
                (now, event)
                for event in projection.attention_events(_all_workflows())
                if event.run_id == run
            ]
            window_start = now - interval
        for ts, event in replay:
            seq += 1
            await emit(EventFrame(seq=seq, ts=ts, event=event))
        seq += 1
        await emit(digest.build_digest(run, window_start, now).model_copy(update={"seq": seq, "ts": now}))
        last = now
        gone = asyncio.create_task(_until_disconnect(socket))
        pending = asyncio.create_task(queue.get())
        try:
            while True:
                remaining = last + interval - time.time()
                done, _ = await asyncio.wait(
                    {pending, gone}, timeout=max(remaining, 0.0),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if gone in done:
                    return
                if pending in done:
                    ts, event = pending.result()
                    pending = asyncio.create_task(queue.get())
                    seq += 1
                    await emit(EventFrame(seq=seq, ts=ts, event=event))
                else:
                    now = time.time()
                    seq += 1
                    frame = digest.build_digest(run, last, now)
                    await emit(frame.model_copy(update={"seq": seq, "ts": now}))
                    last = now
        finally:
            gone.cancel()
            pending.cancel()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("feed for run %s failed", run)
        await socket.close(code=1011, reason=f"feed failed: {type(exc).__name__}: {exc}"[:120])
    finally:
        state.remove_feed(queue)


async def _apply_hello(container_id: str, data: dict) -> None:
    """Fold a sidecar's on-connect ``hello`` into the fleet."""
    identity = data.get("identity") or {}
    snapshot = data.get("snapshot") or {}
    await native._ensure_volumes(container_id)
    wf = state.upsert_workflow(
        container_id,
        name=identity.get("name"),
        repo_name=identity.get("repo_name"),
        repo_branch=identity.get("repo_branch"),
        run_id=identity.get("run_id") or None,
        workflow_type=identity.get("workflow") or None,
    )
    wf.current_node = snapshot.get("current_node") or wf.current_node
    wf.gates.clear()
    if snapshot.get("terminal"):
        wf.state = WorkflowState.FINISHED
        conn = sidecar_hub.get(container_id)
        if conn is not None:
            sidecar_turns.schedule(
                conn,
                run_id=str(identity.get("run_id") or ""),
                workflow=str(identity.get("workflow") or ""),
                final=True,
            )
    else:
        for gate in snapshot.get("gates") or []:
            file_path = str(gate.get("file_path", ""))
            if not file_path:
                continue
            wf.gates[file_path] = GateInfo(workflow_id=container_id, file_path=file_path, question=str(gate.get("question", "")))
        wf.state = WorkflowState.BLOCKED if wf.gates else WorkflowState.RUNNING
    live.mark_fleet()
    live.mark_run(container_id)


async def _apply_socket_progress(container_id: str, data: dict) -> None:
    state.upsert_workflow(container_id, current_node=data.get("current_node"), state=WorkflowState.RUNNING)
    live.mark_fleet()
    live.mark_run(container_id)


def _apply_socket_turn(conn: sidecar_hub.SidecarConnection, data: dict) -> None:
    """A container says one of its turn records moved; go and fetch it, and show a watching pane what the live transcript gained."""
    _TAIL_RUNS[conn.container_id] = str(data.get("run", ""))
    _schedule_tail(conn.container_id)
    sidecar_turns.schedule(
        conn,
        run=str(data.get("run", "")),
        run_id=str(data.get("run_id", "")),
        workflow=str(data.get("workflow", "")),
    )


def _apply_socket_workspace(container_id: str) -> None:
    wf = state.WORKFLOWS.get(container_id)
    if wf is None:
        return
    wf.workspace_rev += 1
    live.mark_run(container_id)


async def _apply_socket_blocked(container_id: str, data: dict) -> None:
    file_path = str(data.get("file_path", ""))
    if not file_path:
        return
    question = str(data.get("question", ""))
    wf = state.upsert_workflow(container_id, state=WorkflowState.BLOCKED)
    wf.gates[file_path] = GateInfo(workflow_id=container_id, file_path=file_path, question=question)
    live.mark_fleet()
    live.mark_run(container_id)
    await alerting._broadcast_notify(f"{wf.name}: {question[:_QUESTION_NOTIFY_LIMIT]}")
    if wf.gates:
        _attend_gates(wf, list(wf.gates.values()))


@websocket("/sidecar")
async def dashboard_sidecar(socket: WebSocket) -> None:
    """The container-dialed data-plane socket (distinct from the browser ``/ws``): the sidecar is the client, so no inbound reachability into the container is needed."""
    await socket.accept()
    conn: sidecar_hub.SidecarConnection | None = None
    try:
        while True:
            data = await socket.receive_json()
            if not isinstance(data, dict):
                continue
            mtype = data.get("type")
            if mtype == "hello":
                container_id = str((data.get("identity") or {}).get("container_id", ""))[:12]
                if not container_id:
                    continue
                conn = sidecar_hub.SidecarConnection(container_id, socket)
                sidecar_hub.register(conn)
                await _apply_hello(container_id, data)
            elif conn is None:
                continue
            elif mtype == "rpc_result":
                conn.resolve(
                    str(data.get("id", "")),
                    ok=bool(data.get("ok")),
                    data=data.get("data"),
                    error=str(data.get("error", "")),
                )
            elif mtype == "progress":
                await _apply_socket_progress(conn.container_id, data)
            elif mtype == "blocked":
                await _apply_socket_blocked(conn.container_id, data)
            elif mtype == "turn":
                _apply_socket_turn(conn, data)
            elif mtype == "workspace":
                _apply_socket_workspace(conn.container_id)
    except WebSocketDisconnect:
        pass
    finally:
        if conn is not None:
            sidecar_hub.unregister(conn)
            live.mark_fleet()
            live.mark_run(conn.container_id)
