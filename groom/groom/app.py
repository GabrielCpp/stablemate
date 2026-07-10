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
from .models import GateInfo, WorkflowContainer, WorkflowState

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
    # Filter the inbox message list; counts stay fleet-wide (the status bar is a
    # dashboard, not a result count), so it is not part of the search response.
    fragment = render.render_inbox(_all_workflows(), q, oob=True)
    return Response(content=fragment, media_type=MediaType.HTML)


@get("/repos", include_in_schema=False)
async def repos() -> Response:
    """The container+repo picker menu: one ``<workflow>-<runid>/<repo>`` entry
    per (container, checkout). There is always one workflow per container, so
    the container name *is* the ``<workflow>-<runid>`` label; a multi-repo
    workspace contributes several entries for the one container. Repos are
    enumerated per container concurrently (each is a throwaway docker run) and
    only for workflows whose workspace volume is known.
    """
    workflows = [wf for wf in _all_workflows() if wf.workspace_volume]

    async def _repos_for(wf: WorkflowContainer) -> tuple:  # (wf, [repo_dir, ...])
        dirs = await asyncio.to_thread(docker_io.list_repo_dirs, wf.workspace_volume)
        return wf, dirs

    resolved = await asyncio.gather(*(_repos_for(wf) for wf in workflows)) if workflows else []
    return Response(content=render.render_repo_menu(resolved), media_type=MediaType.HTML)


@get("/files/{container_id:str}", include_in_schema=False)
async def files(container_id: str, repo: str = "") -> Response:
    """Newline-separated repo-relative file paths for one checkout, fetched
    client-side and turned into a collapsible tree by dashboard.html. ``repo``
    is the volume-relative checkout dir from the picker (empty = volume root).
    """
    wf = state.WORKFLOWS.get(container_id)
    volume = wf.workspace_volume if wf else ""
    if not volume:
        return Response(content="", media_type=MediaType.TEXT)
    paths = await asyncio.to_thread(docker_io.list_files, volume, repo)
    return Response(content="\n".join(paths), media_type=MediaType.TEXT)


@get("/file/{container_id:str}", include_in_schema=False)
async def file_content(container_id: str, repo: str = "", path: str = "") -> Response:
    """Raw text of one file in a checkout, fetched client-side and
    syntax-highlighted by extension (highlight.js) in dashboard.html. The
    combined ``repo/path`` runs through ``safe_relpath`` in docker_io, so a
    crafted path can't escape the mounted volume. "" on any failure or missing
    file — the viewer shows an empty state.
    """
    wf = state.WORKFLOWS.get(container_id)
    volume = wf.workspace_volume if wf else ""
    rel = f"{repo}/{path}".lstrip("/") if repo else path
    if not volume or not rel:
        return Response(content="", media_type=MediaType.TEXT)
    try:
        text = await asyncio.to_thread(docker_io.read_file, volume, rel)
    except ValueError:
        return Response(content="", media_type=MediaType.TEXT)
    return Response(content=text or "", media_type=MediaType.TEXT)


@get("/worker/{container_id:str}", include_in_schema=False)
async def worker_detail(container_id: str) -> Response:
    """The selected worker's detail pane (gate question + answer form + diff),
    fetched on demand into ``#detail`` rather than broadcast — so a live push
    can never wipe a half-typed answer.
    """
    wf = state.WORKFLOWS.get(container_id)
    return Response(content=render.render_worker_detail(wf), media_type=MediaType.HTML)


@get("/diff/{container_id:str}", include_in_schema=False)
async def diff(container_id: str, repo: str = "") -> Response:
    """Plain-text git diff for one checkout's working tree, fetched client-side
    and rendered into HTML by diff2html (see dashboard.html) rather than
    rendered server-side, since diff2html's coloring/file-list needs to run
    in the browser against the raw unified diff text. ``repo`` is the
    volume-relative checkout dir from the picker (empty = first repo found).
    """
    wf = state.WORKFLOWS.get(container_id)
    volume = wf.workspace_volume if wf else ""
    if not volume:
        return Response(content="", media_type=MediaType.TEXT)
    text = await asyncio.to_thread(docker_io.git_diff, volume, repo)
    return Response(content=text, media_type=MediaType.TEXT)


async def _reconcile() -> int:
    """One discovery pass: upsert every found workflow, then prune the ones
    whose container is gone (skipping the prune when docker is unreachable so a
    transient outage never wipes the fleet). Shared by the background startup
    scan and the manual /refresh. Returns the number of workflows found.

    Runs on the default thread-pool via ``asyncio.to_thread``; a Ctrl+C landing
    mid-scan waits for the current docker call to return before the process
    exits (bounded by DOCKER_TIMEOUT), then shuts down cleanly. A daemon-thread
    variant was tried to make that instant but crashed uvloop on teardown, so
    the clean bounded wait is the deliberate choice.
    """
    found = await asyncio.to_thread(discovery.scan)
    for wf in found:
        state.WORKFLOWS[wf.container_id] = wf
    present = await asyncio.to_thread(discovery.present_container_ids)
    if present is not None:
        state.prune_workflows(present)
    return len(found)


@post("/refresh", include_in_schema=False)
async def refresh() -> dict:
    """Re-run the reconciliation scan on demand (e.g. a UI button), so
    workflows that predate this groom process without ever pushing to it are
    still discovered without a restart. Flags SCANNING so an empty fleet shows
    the spinner while the rescan runs.
    """
    state.SCANNING = True
    await _broadcast_shell()
    try:
        count = await _reconcile()
    finally:
        state.SCANNING = False
    await _broadcast_shell()
    return {"ok": True, "count": count}


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


# Held module-side so the background scan task isn't garbage-collected while it
# runs (asyncio keeps only a weak reference to bare tasks).
_scan_task: asyncio.Task | None = None


async def _background_scan() -> None:
    """The startup discovery pass, run off the event loop *after* the server is
    already accepting connections. SCANNING stays True until this finishes (the
    UI shows a spinner); the completion broadcast then swaps in real rows —
    reaching every connected tab through the same path /refresh uses. Cleared in
    a finally so a scan error can't strand the spinner forever.
    """
    try:
        await _reconcile()
    finally:
        state.SCANNING = False
        await _broadcast_shell()


async def _spawn_scan() -> None:
    """on_startup hook: only *schedule* discovery and return immediately, so
    uvicorn finishes lifespan-startup and binds the port right away instead of
    blocking on the whole docker scan (the old _startup_scan did the latter).
    """
    global _scan_task
    _scan_task = asyncio.create_task(_background_scan())


def create_app() -> Litestar:
    return Litestar(
        route_handlers=[
            index,
            search,
            repos,
            files,
            file_content,
            worker_detail,
            diff,
            refresh,
            push_progress,
            push_blocked,
            push_exited,
            dashboard_ws,
            create_static_files_router(path="/assets", directories=[ASSETS_DIR]),
        ],
        on_startup=[_spawn_scan],
    )
