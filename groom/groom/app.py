"""The Litestar web app: dashboard page, one websocket for live push +
answer/restart, HTTP push endpoints for the in-container sidecar (and the
``await_operator.py`` backstop push), and a plain-HTTP search endpoint.

All state lives in :mod:`groom.state` — this module only wires HTTP/websocket
handlers to it.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from litestar import Litestar, Response, get, post, websocket
from litestar.connection import WebSocket
from litestar.enums import MediaType
from litestar.exceptions import WebSocketDisconnect
from litestar.static_files import create_static_files_router

from . import discovery, docker_io, render, state
from .gates import answer_gate
from .models import GateInfo, WorkflowState

ASSETS_DIR = Path(__file__).parent / "assets"
_DASHBOARD_HTML = (Path(__file__).parent / "templates" / "dashboard.html").read_bytes()

_QUESTION_NOTIFY_LIMIT = 200


def _all_workflows() -> list:
    return list(state.WORKFLOWS.values())


async def _broadcast_shell() -> None:
    await state.broadcast(render.render_shell_data(_all_workflows(), oob=True))


async def _ensure_volumes(container_id: str) -> None:
    """Fill in the workspace/runs volume names for a container we've only
    heard about via a sidecar push so far (pushes carry no docker-level
    metadata — only what the container's own env exposes). Cheap enough to
    do on first sight of a container and then never again.
    """
    wf = state.WORKFLOWS.get(container_id)
    if wf and wf.workspace_volume:
        return
    inspect = await asyncio.to_thread(docker_io.docker_inspect, container_id)
    if not inspect:
        return
    found = discovery.container_from_inspect(inspect)
    state.upsert_workflow(
        container_id,
        workspace_volume=found.workspace_volume,
        runs_volume=found.runs_volume,
        workflow_type=found.workflow_type,
    )


@get("/", include_in_schema=False)
async def index() -> Response:
    return Response(content=_DASHBOARD_HTML, media_type=MediaType.HTML)


@get("/search", include_in_schema=False)
async def search(q: str = "") -> Response:
    # Filter the two list regions; counts stay fleet-wide (the status bar is a
    # dashboard, not a result count), so it is not part of the search response.
    workflows = _all_workflows()
    fragment = render.render_tree(workflows, q, oob=True) + render.render_inbox(workflows, q, oob=True)
    return Response(content=fragment, media_type=MediaType.HTML)


@get("/worker/{container_id:str}", include_in_schema=False)
async def worker_detail(container_id: str) -> Response:
    """The selected worker's detail pane (gate question + answer form + diff),
    fetched on demand into ``#detail`` rather than broadcast — so a live push
    can never wipe a half-typed answer.
    """
    wf = state.WORKFLOWS.get(container_id)
    return Response(content=render.render_worker_detail(wf), media_type=MediaType.HTML)


@get("/diff/{container_id:str}", include_in_schema=False)
async def diff(container_id: str) -> Response:
    """Plain-text git diff for a workflow's working tree, fetched client-side
    and rendered into HTML by diff2html (see dashboard.html) rather than
    rendered server-side, since diff2html's coloring/file-list needs to run
    in the browser against the raw unified diff text.
    """
    wf = state.WORKFLOWS.get(container_id)
    volume = wf.workspace_volume if wf else ""
    if not volume:
        return Response(content="", media_type=MediaType.TEXT)
    text = await asyncio.to_thread(docker_io.git_diff, volume)
    return Response(content=text, media_type=MediaType.TEXT)


@post("/refresh", include_in_schema=False)
async def refresh() -> dict:
    """Re-run the startup reconciliation scan on demand (e.g. a UI button),
    so workflows that predate this groom process without ever pushing to it
    are still discovered without a restart.
    """
    found = await asyncio.to_thread(discovery.scan)
    for wf in found:
        state.WORKFLOWS[wf.container_id] = wf
    present = await asyncio.to_thread(discovery.present_container_ids)
    if present is not None:
        state.prune_workflows(present)
    await _broadcast_shell()
    return {"ok": True, "count": len(found)}


@post("/push/progress", include_in_schema=False)
async def push_progress(data: dict) -> dict:
    container_id = str(data.get("container_id", ""))[:12]
    if not container_id:
        return {"ok": False}
    await _ensure_volumes(container_id)
    state.upsert_workflow(
        container_id,
        name=data.get("name"),
        repo_name=data.get("repo_name"),
        repo_branch=data.get("repo_branch"),
        current_node=data.get("current_node"),
        state=WorkflowState.RUNNING,
    )
    await _broadcast_shell()
    return {"ok": True}


@post("/push/blocked", include_in_schema=False)
async def push_blocked(data: dict) -> dict:
    """Used both by groom-sidecar and by the await_operator.py backstop push
    — same shape, same handling, whichever gets there first (or both; the
    second call is just a harmless re-render).
    """
    container_id = str(data.get("container_id", ""))[:12]
    file_path = str(data.get("file_path", ""))
    if not container_id or not file_path:
        return {"ok": False}
    await _ensure_volumes(container_id)
    question = str(data.get("question", ""))
    wf = state.upsert_workflow(
        container_id,
        name=data.get("name"),
        repo_name=data.get("repo_name"),
        repo_branch=data.get("repo_branch"),
        state=WorkflowState.BLOCKED,
    )
    wf.gates[file_path] = GateInfo(workflow_id=container_id, file_path=file_path, question=question)

    fragment = render.render_shell_data(_all_workflows(), oob=True)
    fragment += render.render_notify_script(f"{wf.name}: {question[:_QUESTION_NOTIFY_LIMIT]}")
    await state.broadcast(fragment)
    return {"ok": True}


@post("/push/exited", include_in_schema=False)
async def push_exited(data: dict) -> dict:
    """The workflow process ended (fired once by the container entrypoint via
    ``groom-sidecar --exit-code``). Mark it FINISHED and drop any open gate —
    a container that has exited can't act on an answer. The container object
    usually still exists until ``docker rm``; the refresh/startup prune is what
    removes it from the list entirely.
    """
    container_id = str(data.get("container_id", ""))[:12]
    if not container_id:
        return {"ok": False}
    await _ensure_volumes(container_id)
    exit_code = data.get("exit_code")
    wf = state.upsert_workflow(
        container_id,
        name=data.get("name"),
        repo_name=data.get("repo_name"),
        repo_branch=data.get("repo_branch"),
        state=WorkflowState.FINISHED,
        exit_code=int(exit_code) if isinstance(exit_code, (int, str)) and str(exit_code).lstrip("-").isdigit() else None,
    )
    wf.gates.clear()
    await _broadcast_shell()
    return {"ok": True}


async def _handle_command(data: dict) -> None:
    if data.get("cmd") != "answer":
        return
    container_id = str(data.get("workflow_id", ""))
    file_path = str(data.get("file_path", ""))
    answer = str(data.get("answer", ""))
    wf = state.WORKFLOWS.get(container_id)
    workspace_volume = wf.workspace_volume if wf else ""
    result = await answer_gate(container_id, file_path, answer, workspace_volume=workspace_volume)
    state.record_log(
        {"event": "answer", "container_id": container_id, "file_path": file_path, "ok": result.ok, "message": result.message}
    )
    # A worker whose last gate just cleared is no longer blocked — answer_gate
    # woke/started it, so reflect RUNNING immediately instead of leaving a
    # gate-less BLOCKED ghost until the next progress push.
    if result.ok and wf is not None and not wf.gates and wf.state == WorkflowState.BLOCKED:
        wf.state = WorkflowState.RUNNING

    fragment = render.render_shell_data(_all_workflows(), oob=True)
    if result.ok:
        fragment += render.render_answered_script(container_id, file_path)
    await state.broadcast(fragment)


async def _send_loop(socket: WebSocket, queue: asyncio.Queue) -> None:
    while True:
        html = await queue.get()
        await socket.send_text(html)


async def _recv_loop(socket: WebSocket) -> None:
    while True:
        data = await socket.receive_json()
        await _handle_command(data)


@websocket("/ws")
async def dashboard_ws(socket: WebSocket) -> None:
    await socket.accept()
    queue: asyncio.Queue = asyncio.Queue()
    state.add_client(queue)
    try:
        await socket.send_text(render.render_shell_data(_all_workflows(), oob=True))
        send_task = asyncio.create_task(_send_loop(socket, queue))
        recv_task = asyncio.create_task(_recv_loop(socket))
        done, pending = await asyncio.wait({send_task, recv_task}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            exc = task.exception()
            if exc is not None and not isinstance(exc, WebSocketDisconnect):
                raise exc
    finally:
        state.remove_client(queue)


async def _startup_scan() -> None:
    found = await asyncio.to_thread(discovery.scan)
    for wf in found:
        state.WORKFLOWS[wf.container_id] = wf
    present = await asyncio.to_thread(discovery.present_container_ids)
    if present is not None:
        state.prune_workflows(present)


def create_app() -> Litestar:
    return Litestar(
        route_handlers=[
            index,
            search,
            worker_detail,
            diff,
            refresh,
            push_progress,
            push_blocked,
            push_exited,
            dashboard_ws,
            create_static_files_router(path="/assets", directories=[ASSETS_DIR]),
        ],
        on_startup=[_startup_scan],
    )
