"""The Litestar web app: dashboard page, one websocket for live push + answer/restart, HTTP push endpoints for the in-container sidecar (and the ``await_operator.py`` backstop push), the JSON read endpoints the browser fetches per selection, and the OTLP collector endpoints (``/v1/traces``, ``/v1/metrics``) that make groom the default local backend for workhorse's opt-in OpenTelemetry instrumentation."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from litestar import Litestar, Request, Response, delete, get, post, websocket
from litestar.connection import WebSocket
from litestar.enums import MediaType
from litestar.exceptions import WebSocketDisconnect
from litestar.params import PathParameter, QueryParameter
from litestar.static_files import create_static_files_router

from groom import (
    alerts,
    archive,
    attend,
    attend_transcript,
    discovery,
    dispatch,
    docker_io,
    localfs,
    notify,
    otlp,
    pools,
    projection,
    sidecar_hub,
    sidecar_turns,
    state,
    store,
    turns,
)
from groom.attention import RULE_EVENTS, AttentionEvent, AttentionFrame
from groom.gates import answer_gate
from groom.live_history import LiveHistory
from groom.models import AnswerResult, GateInfo, RunTelemetry, WorkflowContainer, WorkflowState
from workhorse import control, inbox
from workhorse import reload as reload_mod
from workhorse._vendor.stablemate_core import config as core_config

logger = logging.getLogger(__name__)

ASSETS_DIR = Path(__file__).parent / "assets"

_ASSET_URL_RE = re.compile(rb'(?:href|src)="(/assets/([^"?]+))"')


def stamp_assets(html: bytes) -> bytes:
    """Version every ``/assets/...`` URL in the shell with that file's mtime+size."""

    def stamp(match: re.Match[bytes]) -> bytes:
        url, name = match.group(1), match.group(2).decode()
        try:
            info = (ASSETS_DIR / name).stat()
        except OSError:
            return match.group(0)
        version = f"{int(info.st_mtime)}-{info.st_size}".encode()
        return match.group(0).replace(url, url + b"?v=" + version)

    return _ASSET_URL_RE.sub(stamp, html)


_DASHBOARD_HTML = stamp_assets(
    (Path(__file__).parent / "templates" / "dashboard.html").read_bytes()
)

_QUESTION_NOTIFY_LIMIT = 200

RULES_TICK_S = float(os.environ.get("GROOM_RULES_TICK_S", "60"))
PRUNE_EVERY_S = float(os.environ.get("GROOM_PRUNE_EVERY_S", "3600"))
HARVEST_EVERY_S = float(os.environ.get("GROOM_HARVEST_EVERY_S", "300"))
LIVE_TICK_S = float(os.environ.get("GROOM_LIVE_TICK_S", "5"))
ARCHIVE_EVERY_S = archive.ARCHIVE_EVERY_S


def _all_workflows() -> list:
    return list(state.WORKFLOWS.values())


async def _broadcast_shell(changed: str = "") -> None:
    """Push the fleet to every tab, and — when one run is what changed — that run's detail slices to the tabs watching it."""
    await state.broadcast(projection.state_message(_all_workflows()))
    if changed:
        await _push_detail(changed)


async def _detail_message(wf: WorkflowContainer) -> dict:
    """One run's detail pane, addressed to the tabs watching that run."""
    tel, facts, logs, history = await _run_facts(wf)
    return projection.detail_message(wf, tel, facts, logs, history=history)


async def _push_detail(container_id: str) -> None:
    """Send one run's detail slices to the tabs watching that run, and nobody else."""
    watchers = state.watchers_of(container_id)
    if not watchers:
        return
    wf = state.WORKFLOWS.get(container_id)
    if wf is None:
        return
    message = await _detail_message(wf)
    for queue in watchers:
        await state.send(queue, message)


async def _push_watched() -> None:
    """Refresh every open detail pane on the clock, for the same reason the run list is re-pushed on one: elapsed labels are derived from ``now``."""
    for run_id in state.watched_ids():
        await _push_detail(run_id)


async def _broadcast_notify(message: str) -> None:
    """A one-shot alert for the tabs to toast (and raise a browser notification for)."""
    await state.broadcast({"type": "notify", "message": message})


async def _ensure_volumes(container_id: str) -> None:
    """Fill in the workspace/runs volume names for a container we've only heard about via a sidecar push so far (pushes carry no docker-level metadata — only what the container's own env exposes)."""
    wf = state.WORKFLOWS.get(container_id)
    if wf and wf.native:
        return
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


def _sync_native_row(run: RunTelemetry, fired: list[alerts.Alert] | None = None) -> bool:
    """Project a run's telemetry hot-cache entry onto a dashboard row when the run is **native** — i.e."""
    if run.native is None:
        run.native = localfs.is_local_dir(run.run_dir) or localfs.is_local_dir(
            run.workspace
        )
    if not run.native:
        return False
    before = state.WORKFLOWS.get(run.run_id)
    prev = (
        (before.state, before.current_node, before.activity, before.last_session,
         tuple((g.file_path, g.question, g.kind) for g in before.gates.values()))
        if before
        else None
    )
    if not run.terminal and run.wait_kind in ("operator", "machine"):
        gate = GateInfo(
            workflow_id=run.run_id,
            file_path=run.wait_gate_path,
            question=run.wait_gate_question,
            kind=run.wait_kind,
        )
    else:
        gate = None
    gates = {gate.file_path: gate} if gate is not None else {}
    if run.terminal:
        new_state = WorkflowState.FINISHED
    elif gates:
        new_state = WorkflowState.BLOCKED
    else:
        new_state = WorkflowState.RUNNING
    wf = state.upsert_workflow(
        run.run_id,
        name=run.workflow or run.run_id[:12],
        native=True,
        workflow_type=run.workflow,
        repo_name=run.repo,
        repo_branch=run.branch,
        run_id=run.run_id,
        workspace_volume=run.workspace,
        runs_volume=run.run_dir,
        current_node=run.current_node,
        activity=run.activity,
        pid=run.pid,
        state=new_state,
    )
    wf.gates = dict(gates)
    wf.last_session = run.last_session
    _attend_gates(wf, list(wf.gates.values()))
    return prev is None or prev != (
        wf.state,
        wf.current_node,
        wf.activity,
        wf.last_session,
        tuple((g.file_path, g.question, g.kind) for g in wf.gates.values()),
    )


async def _project_native_rows(records: list) -> None:
    """After an OTLP ingest, refresh the dashboard rows of the native runs it touched and broadcast once if any changed."""
    run_ids = {r.get("run_id") for r in records if r.get("run_id")}
    changed = []
    newly_blocked = []
    fired: list[alerts.Alert] = []
    for run_id in run_ids:
        run = state.RUNS.get(run_id)
        if run is None:
            continue
        existing = state.WORKFLOWS.get(run_id)
        was_blocked = (
            existing is not None
            and existing.state == WorkflowState.BLOCKED
            and existing.last_session == run.last_session
        )
        changed.append(_sync_native_row(run, fired))
        wf = state.WORKFLOWS.get(run_id)
        if wf is not None and wf.state == WorkflowState.BLOCKED and not was_blocked:
            newly_blocked.append(wf)
    await _dispatch_alerts(fired)
    if any(changed):
        await _broadcast_shell()
        for run_id in run_ids:
            await _push_detail(run_id)
    for wf in newly_blocked:
        if wf.gates:
            gate = next(iter(wf.gates.values()))
            await _broadcast_notify(
                f"{wf.workflow_type or wf.name} is waiting on {gate.file_path}"
            )


@get("/", include_in_schema=False)
async def index() -> Response:
    return Response(content=_DASHBOARD_HTML, media_type=MediaType.HTML)


@get("/api/state", include_in_schema=False)
async def api_state(q: Annotated[str, QueryParameter()] = "") -> dict:
    """The whole fleet as JSON — **the same payload the websocket pushes**."""
    return projection.state_message(_all_workflows(), q)


@get("/repos", include_in_schema=False)
async def repos() -> list[dict]:
    """The container+repo picker's contents: one group per container, each with the checkouts found on its volume."""
    workflows = [wf for wf in _all_workflows() if wf.workspace_volume]

    async def _repos_for(wf: WorkflowContainer) -> tuple:
        lister = localfs.list_repo_dirs if wf.native else docker_io.list_repo_dirs
        dirs = await asyncio.to_thread(lister, wf.workspace_volume)
        return wf, dirs

    resolved = await asyncio.gather(*(_repos_for(wf) for wf in workflows)) if workflows else []
    return projection.repo_entries(list(resolved))


async def _sidecar_rpc(container_id: str, method: str, params: dict) -> dict | None:
    """Serve a data-plane read from the container's live sidecar socket, or ``None`` when no sidecar is connected or the RPC fails — the caller then falls back to the throwaway-container volume read."""
    conn = sidecar_hub.get(container_id)
    if conn is None:
        return None
    try:
        return await conn.rpc(method, params)
    except sidecar_hub.SidecarError:
        return None


@get("/files/{container_id:str}", include_in_schema=False)
async def files(
    container_id: Annotated[str, PathParameter()],
    repo: Annotated[str, QueryParameter()] = "",
) -> dict:
    """The repo-relative file paths of one checkout, as ``{"paths": [...]}``."""
    served = await _sidecar_rpc(container_id, "getTree", {"repo": repo})
    if served is not None:
        return {"paths": list(served.get("paths") or [])}

    wf = state.WORKFLOWS.get(container_id)
    volume = wf.workspace_volume if wf else ""
    if not volume:
        return {"paths": []}
    reader = localfs.list_files if wf and wf.native else docker_io.list_files
    paths = await asyncio.to_thread(reader, volume, repo)
    return {"paths": list(paths)}


@get("/file/{container_id:str}", include_in_schema=False)
async def file_content(
    container_id: Annotated[str, PathParameter()],
    repo: Annotated[str, QueryParameter()] = "",
    path: Annotated[str, QueryParameter()] = "",
) -> dict:
    """One file's text plus the highlight.js language its name implies, as ``{"path", "content", "lang"}``."""
    lang = projection.file_lang(path)
    served = await _sidecar_rpc(container_id, "getFile", {"repo": repo, "path": path})
    if served is not None:
        return {"path": path, "content": served.get("content") or "", "lang": lang}

    wf = state.WORKFLOWS.get(container_id)
    volume = wf.workspace_volume if wf else ""
    rel = f"{repo}/{path}".lstrip("/") if repo else path
    if wf and wf.native and not repo:
        gates = projection.reported_gates(wf, projection.telemetry_for(wf))
        gate = next((gate for gate in gates if gate.file_path == path), None)
        if gate is not None:
            absolute = Path(_gate_abs_path(wf, gate))
            if absolute.is_absolute():
                volume, rel = str(absolute.parent), absolute.name
    if not volume or not rel:
        return {"path": path, "content": "", "lang": lang}
    reader = localfs.read_file if wf and wf.native else docker_io.read_file
    try:
        text = await asyncio.to_thread(reader, volume, rel)
    except ValueError:
        return {"path": path, "content": "", "lang": lang}
    return {"path": path, "content": text or "", "lang": lang}


async def _run_facts(wf: WorkflowContainer) -> tuple:
    """Seed history once per subscription; compose subsequent pushes in memory."""
    run_id = projection.run_id_of(wf)
    history = state.HISTORIES.get(run_id)
    if history is None or not history.loaded:
        async with state.HISTORY_LOCK:
            history = state.HISTORIES.get(run_id)
            if history is None:
                history = LiveHistory(log_limit=projection.LOG_TRAIL_LIMIT)
            if run_id and not history.loaded:
                spans = await pools.QUERY.run(store.detail_spans, run_id)
                logs = await pools.QUERY.run(
                    store.query_logs, run=run_id, limit=projection.LOG_TRAIL_LIMIT
                )
                metric_rows = await pools.QUERY.run(
                    store.detail_metrics, run_id, projection.LOG_TRAIL_LIMIT
                )
                history.update_spans(spans)
                history.logs = logs
                history.metrics = metric_rows
                history.loaded = True
            if state.watchers_of(wf.container_id):
                state.HISTORIES[run_id] = history
    facts = next(iter(alerts.live_status(run=run_id)), {}) if run_id else {}
    facts.update(history.facts())
    return state.RUNS.get(run_id), facts, history.logs, history.recent()


async def _store_history_batch(
    rows: list[dict], writer: Callable[[list[dict]], None], *,
    kind: Literal["spans", "logs", "metrics"] = "spans"
) -> None:
    """Commit and advance watched snapshots atomically with respect to seeding."""
    async with state.HISTORY_LOCK:
        histories = {
            run_id: state.HISTORIES[run_id]
            for run_id in sorted({row["run_id"] for row in rows})
            if run_id in state.HISTORIES
        }
        await pools.INGEST.run(writer, rows)
        for run_id, history in histories.items():
            batch = [row for row in rows if row["run_id"] == run_id]
            if kind == "logs":
                history.update_logs(batch)
            elif kind == "metrics":
                history.update_metrics(batch)
            else:
                history.update_spans(batch)


async def _push_received(rows: list[dict]) -> None:
    run_ids = {row["run_id"] for row in rows}
    for cid in state.watched_ids():
        wf = state.WORKFLOWS.get(cid)
        if wf is not None and projection.run_id_of(wf) in run_ids:
            await _push_detail(cid)


@get("/worker/{container_id:str}", include_in_schema=False)
async def worker_detail(container_id: Annotated[str, PathParameter()]) -> dict:
    """One run's detail pane as JSON — activity, its gates, live metrics, log trail."""
    wf = state.WORKFLOWS.get(container_id)
    if wf is None:
        return {"found": False, "id": container_id}
    tel, facts, logs, history = await _run_facts(wf)
    return projection.run_detail(wf, tel, facts, logs, history=history)


@get("/diff/{container_id:str}", include_in_schema=False)
async def diff(
    container_id: Annotated[str, PathParameter()],
    repo: Annotated[str, QueryParameter()] = "",
) -> dict:
    """One checkout's working-tree git diff, as ``{"diff": "<unified diff>"}``."""
    served = await _sidecar_rpc(container_id, "getDiff", {"repo": repo})
    if served is not None:
        return {"diff": served.get("diff") or ""}

    wf = state.WORKFLOWS.get(container_id)
    volume = wf.workspace_volume if wf else ""
    if not volume:
        return {"diff": ""}
    differ = localfs.git_diff if wf and wf.native else docker_io.git_diff
    text = await asyncio.to_thread(differ, volume, repo)
    return {"diff": text or ""}


@get("/api/run/{run_id:str}/outbox", include_in_schema=False)
async def outbox_get(run_id: Annotated[str, PathParameter()]) -> dict:
    """The gate this run is parked on, if any — its path, question and status."""
    wf = _workflow_by_run_id(run_id)
    if wf is None:
        return {"found": False}
    gate = next(iter(projection.reported_gates(wf, projection.telemetry_for(wf))), None)
    if gate is None:
        return {"found": False}
    return {
        "found": True,
        "file_path": gate.file_path,
        "question": gate.question,
        "status": gate.status,
    }


@post("/api/run/{run_id:str}/outbox", include_in_schema=False)
async def outbox_post(run_id: Annotated[str, PathParameter()], data: dict) -> dict:
    """Answer the gate this run is parked on."""
    wf = _workflow_by_run_id(run_id)
    if wf is None:
        return {"ok": False, "message": "no such run"}
    file_path = str(data.get("file_path", ""))
    answer = str(data.get("answer", ""))
    result = await _answer(wf, wf.container_id, file_path, answer)
    return {"ok": result.ok, "message": result.message}


@get("/api/run/{run_id:str}/inbox", include_in_schema=False)
async def inbox_get(
    run_id: Annotated[str, PathParameter()],
    include_all: Annotated[bool, QueryParameter()] = False,
) -> dict:
    """This run's inbox — outstanding messages by default, every message (replied or not) when ``?include_all=true`` — mirroring the CLI's ``read``."""
    wf = _workflow_by_run_id(run_id)
    if wf is None:
        return {"messages": []}
    messages = await asyncio.to_thread(_inbox_messages, wf)
    if not include_all:
        messages = [m for m in messages if not m.reply]
    return {"messages": [m.model_dump() for m in messages]}


@post("/api/run/{run_id:str}/inbox", include_in_schema=False)
async def inbox_post(run_id: Annotated[str, PathParameter()], data: dict) -> dict:
    """Append an operator message to this run's inbox — the ``ask`` verb, reachable over HTTP rather than only the CLI so a browser tab (or a babysitting session without shell access to the run dir) can leave one."""
    wf = _workflow_by_run_id(run_id)
    if wf is None:
        return {"ok": False, "message": "no such run"}
    body = str(data.get("body", ""))
    if not body:
        return {"ok": False, "message": "message body is required"}
    message_id = str(data.get("id") or uuid.uuid4().hex[:12])
    at = datetime.now(UTC).isoformat()
    message = await asyncio.to_thread(_inbox_append, wf, message_id=message_id, body=body, at=at)
    if message is None:
        return {"ok": False, "message": "no run directory yet"}
    return {"ok": True, "message": message.model_dump()}


async def _reconcile() -> int:
    """One discovery pass: upsert every found workflow, then prune the ones whose container is gone (skipping the prune when docker is unreachable so a transient outage never wipes the fleet)."""
    found = await asyncio.to_thread(discovery.scan)
    for wf in found:
        state.WORKFLOWS[wf.container_id] = wf
    present = await asyncio.to_thread(discovery.present_container_ids)
    if present is not None:
        state.prune_workflows(present)
    return len(found)


@post("/refresh", include_in_schema=False)
async def refresh() -> dict:
    """Re-run the reconciliation scan on demand (e.g."""
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
    await _broadcast_shell(container_id)
    return {"ok": True}


@get("/api/attend/queue", include_in_schema=False)
async def attend_queue() -> dict:
    """Every run currently waiting on an attendant, oldest first — the whole fleet."""
    return {"mode": attend.mode(), "jobs": attend.queue()}


@get("/api/attend/sessions", include_in_schema=False)
async def attend_sessions() -> dict:
    """The attendance log: the latest 200, newest first."""
    rows = await asyncio.to_thread(store.attend_recent, 200)
    return {"mode": attend.mode(), "sessions": rows}


@get("/api/attend/sessions/{session_id:str}", include_in_schema=False)
async def attend_session(session_id: Annotated[str, PathParameter()]) -> dict:
    """One attendance, rendered as a conversation — not as JSON."""
    row = await asyncio.to_thread(store.attend_by_session, session_id)
    await asyncio.to_thread(attend_transcript.ensure_body, session_id)
    rendered = await asyncio.to_thread(attend_transcript.render_session, session_id)
    workspace = str((row or {}).get("workspace") or "")
    resume = f"claude --resume {session_id}"
    rendered["resume"] = f"cd {workspace} && {resume}" if workspace else resume
    rendered["record"] = row
    rendered["attempts"] = list((row or {}).get("session_ids") or [])
    return rendered


@post("/api/attend/sessions/{job_id:str}/stop", include_in_schema=False)
async def attend_stop(job_id: Annotated[str, PathParameter()]) -> dict:
    """Kill this attendant and hand its run back to the operator's own terminal."""
    stopped = await asyncio.to_thread(attend.stop, job_id)
    await _broadcast_shell()
    return {"ok": stopped}


@get("/api/settings/attend", include_in_schema=False)
async def attend_settings_get() -> dict:
    """The effective attend settings, and where each value came from."""
    return (await asyncio.to_thread(attend.settings)).as_dict()


@post("/api/settings/attend", include_in_schema=False)
async def attend_settings_post(data: dict) -> dict:
    """Turn the attendant on or off, persisted to the unified home config."""
    current = await asyncio.to_thread(attend.settings)
    enabled = bool(data.get("enabled"))
    wanted = (current.last_mode or attend.HEADLESS) if enabled else attend.OFF
    updated = core_config.AttendSettings(
        mode=wanted,
        last_mode=current.last_mode if wanted == attend.OFF else wanted,
        cli=current.cli,
        deny=current.deny,
    )
    await asyncio.to_thread(core_config.write_attend_settings, updated)
    attend.forget_settings()
    await _broadcast_shell()
    return (await asyncio.to_thread(attend.settings)).as_dict()


@get("/api/dispatch/queues", include_in_schema=False)
async def dispatch_queues() -> dict:
    """Every configured queue, with its concurrency and current occupancy."""
    return {"queues": await asyncio.to_thread(dispatch.queue_status)}


@post("/api/dispatch/{queue:str}/items", include_in_schema=False)
async def dispatch_enqueue(queue: Annotated[str, PathParameter()], data: dict) -> Response:
    """Enqueue one item onto this queue."""
    params = data.get("params") if isinstance(data.get("params"), dict) else {}
    try:
        item = await asyncio.to_thread(dispatch.enqueue, queue, params)
    except dispatch.UnknownQueue:
        return Response(content={"ok": False, "error": f"no such queue: {queue}"}, status_code=404)
    await _broadcast_shell()
    return Response(content={"ok": True, "item": item})


@get("/api/dispatch/{queue:str}/items", include_in_schema=False)
async def dispatch_items(queue: Annotated[str, PathParameter()]) -> dict:
    """This queue's items, newest first — the latest 200, same cap `attend_sessions` uses."""
    rows = await asyncio.to_thread(store.dispatch_list, queue, 200)
    return {"items": rows}


@delete("/api/dispatch/{queue:str}/items/{item_id:str}", include_in_schema=False, status_code=200)
async def dispatch_delete(
    queue: Annotated[str, PathParameter()], item_id: Annotated[str, PathParameter()]
) -> dict:
    """Cancel a still-`pending` item before it ever spawns."""
    del queue
    return {"ok": await asyncio.to_thread(dispatch.cancel_pending, item_id)}


@post("/api/dispatch/{queue:str}/items/{item_id:str}/stop", include_in_schema=False)
async def dispatch_stop(
    queue: Annotated[str, PathParameter()], item_id: Annotated[str, PathParameter()]
) -> dict:
    """Kill this item's process and free its queue slot for the next `pending` one."""
    del queue
    stopped = await asyncio.to_thread(dispatch.stop, item_id)
    await _broadcast_shell()
    return {"ok": stopped}


@post("/push/blocked", include_in_schema=False)
async def push_blocked(data: dict) -> dict:
    """Used both by groom-sidecar and by the await_operator.py backstop push — same shape, same handling, whichever gets there first (or both; the second call is just a harmless re-render)."""
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

    await _broadcast_shell(container_id)
    await _broadcast_notify(f"{wf.name}: {question[:_QUESTION_NOTIFY_LIMIT]}")
    gate = next(iter(wf.gates.values()))
    _attend_gates(wf, [gate])
    return {"ok": True}


@post("/push/exited", include_in_schema=False)
async def push_exited(data: dict) -> dict:
    """The workflow process ended (fired once by the container entrypoint via ``groom-sidecar --exit-code``)."""
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
    attend.release(container_id)
    if wf.exit_code is not None and wf.exit_code not in _NOT_A_DEATH_EXIT:
        _attend_death(container_id)
    await _broadcast_shell(container_id)
    return {"ok": True}


_NOT_A_DEATH_EXIT = frozenset({0, reload_mod.RELOAD_EXIT_CODE})
_NOT_A_DEATH_TERMINAL = frozenset(alerts.CLEAN_TERMINALS) | {"interrupted", "reload"}


def _attend_death(container_id: str) -> None:
    """Put an attendant on a run that ended without reaching its own end."""
    wf = state.WORKFLOWS.get(container_id)
    if wf is None or not wf.native:
        return
    try:
        attend.attend_death(
            run_id=wf.container_id,
            workflow=wf.workflow_type or wf.name,
            run_dir=wf.runs_volume,
            workspace=wf.workspace_volume,
        )
    except Exception:
        logger.exception("attend: dead-run dispatch failed for %s", container_id)


async def _dispatch_alerts(fired: list[alerts.Alert]) -> None:
    """Fan one batch of newly-fired alerts out to every channel: the activity log, the AFK push (ntfy/webhook, off the event loop — urllib blocks), and the browser notification path blocked-gates already use."""
    for alert in fired:
        telemetry = state.RUNS.get(alert.run_id)
        await state.broadcast(AttentionFrame(events=[AttentionEvent(
            run_id=alert.run_id, event=RULE_EVENTS[alert.rule], message=alert.message,
            node=telemetry.current_node if telemetry else "",
            question=telemetry.wait_gate_question if telemetry else "",
            gate_path=telemetry.wait_gate_path if telemetry else "",
            terminal=telemetry.terminal if telemetry else "",
        )]).model_dump())
        state.record_log(
            {"event": "alert", "rule": alert.rule, "run_id": alert.run_id, "message": alert.message}
        )
        if alert.rule == "DIED" or (
            alert.rule == "ENDED"
            and (run := state.RUNS.get(alert.run_id)) is not None
            and run.terminal not in _NOT_A_DEATH_TERMINAL
        ):
            _attend_death(alert.run_id)
        await asyncio.to_thread(notify.push, f"groom: {alert.rule}", alert.message)
        await _broadcast_notify(f"[{alert.rule}] {alert.message}")


def _real_runs(records: list[dict]) -> list[dict]:
    """Drop records a test process produced, before anything stores or alerts on them."""
    return [r for r in records if not store.is_test_run_dir(str(r.get("run_dir", "")))]


def _truthy(value: str) -> bool:
    """A query flag, read the way a checkbox writes it (`1`, `on`) and the way a hand-typed URL does (`true`, `yes`)."""
    return value.strip().lower() in ("1", "true", "yes", "on")


_RETRY_AFTER_S = "5"


def _store_unavailable() -> Response:
    return Response(
        content=b"",
        status_code=503,
        media_type="application/x-protobuf",
        headers={"Retry-After": _RETRY_AFTER_S},
    )


@post("/v1/traces", include_in_schema=False)
async def otlp_traces(request: Request) -> Response:
    """Standard OTLP/HTTP trace receiver — parse → store → eval rules → broadcast, mirroring push_blocked's shape."""
    body = b""
    try:
        body = await request.body()
        spans = _real_runs(otlp.parse_traces(body))
    except Exception as exc:  # noqa: BLE001 - undecodable payload, whatever the cause → 400
        logger.warning(
            "OTLP traces rejected from %s content-type=%r content-encoding=%r "
            "content-length=%r body-bytes=%d: %s: %s",
            request.client,
            request.headers.get("content-type"),
            request.headers.get("content-encoding"),
            request.headers.get("content-length"),
            len(body),
            type(exc).__name__,
            exc,
        )
        return Response(content=b"", status_code=400, media_type="application/x-protobuf")
    try:
        await _store_history_batch(spans, store.insert_spans)
    except sqlite3.Error:
        return _store_unavailable()
    await _dispatch_alerts(alerts.ingest_spans(spans))
    await _project_native_rows(spans)
    await _push_received(spans)
    return Response(content=b"", media_type="application/x-protobuf", status_code=200)


@post("/v1/metrics", include_in_schema=False)
async def otlp_metrics(request: Request) -> Response:
    """Standard OTLP/HTTP metric receiver."""
    try:
        points = _real_runs(otlp.parse_metrics(await request.body()))
    except Exception:  # noqa: BLE001 - undecodable payload, whatever the cause → 400
        return Response(content=b"", status_code=400, media_type="application/x-protobuf")
    try:
        await _store_history_batch(points, store.insert_metrics, kind="metrics")
    except sqlite3.Error:
        return _store_unavailable()
    await _dispatch_alerts(alerts.ingest_metrics(points))
    await _project_native_rows(points)
    await _push_received(points)
    return Response(content=b"", media_type="application/x-protobuf", status_code=200)


@post("/v1/logs", include_in_schema=False)
async def otlp_logs(request: Request) -> Response:
    """Standard OTLP/HTTP log receiver."""
    try:
        records = _real_runs(otlp.parse_logs(await request.body()))
    except Exception:  # noqa: BLE001 - undecodable payload, whatever the cause → 400
        return Response(content=b"", status_code=400, media_type="application/x-protobuf")
    try:
        await _store_history_batch(records, store.insert_logs, kind="logs")
    except sqlite3.Error:
        return _store_unavailable()
    await _push_received(records)
    return Response(content=b"", media_type="application/x-protobuf", status_code=200)




@get("/api/live", include_in_schema=False)
async def api_live(run: Annotated[str, QueryParameter()] = "") -> list[dict]:
    """Where each live run is right now — the rows behind ``groom status``."""
    return alerts.live_status(run=run)




def _attend_gates(wf: WorkflowContainer, gates: list[GateInfo]) -> None:
    """Put an attendant on the gates this row reports being parked on."""
    if not wf.native:
        return
    try:
        if not wf.gates:
            attend.release(wf.container_id)
            return
        for gate in gates:
            attend.attend_gate(
                run_id=wf.container_id,
                workflow=wf.workflow_type or wf.name,
                run_dir=wf.runs_volume,
                workspace=wf.workspace_volume,
                gate_path=_gate_abs_path(wf, gate),
                question=gate.question,
                kind=gate.kind or attend.ATTENDABLE_KIND,
            )
    except Exception:
        logger.exception("attend: dispatch failed for %s", wf.container_id)


def _same_gate(run_path: str, file_path: str) -> bool:
    """Whether the path a run reports for its gate names the same file as the (possibly workspace-relative) path a groom row carries."""
    rel = file_path.lstrip("/")
    return bool(run_path) and (run_path == file_path or run_path.endswith(f"/{rel}"))


async def _answer_via_socket(
    wf: WorkflowContainer | None, file_path: str, answer: str
) -> AnswerResult | None:
    """Deliver one answer over the run's control socket, or ``None`` when the file fallback should decide instead."""
    if wf is None:
        return None
    listing = await _run_questions(wf)
    if not listing or not listing.get("ok"):
        return None
    questions = [q for q in listing.get("questions") or [] if isinstance(q, dict)]
    match = next(
        (q for q in questions if _same_gate(str(q.get("path", "")), file_path)), None
    )
    if match is None:
        return None
    request = control.Request(
        action=control.ANSWER, path=str(match.get("path", "")), body=answer
    )
    if wf.native:
        try:
            reply = await asyncio.to_thread(control.send, wf.runs_volume, request)
        except (FileNotFoundError, control.ControlProtocolError):
            return None
    else:
        try:
            reply = await sidecar_hub.answer_gate(
                wf.container_id, "", request.path, answer
            )
        except sidecar_hub.SidecarError:
            return None
        if reply.get("error") == "no listener":
            return None
    if not reply:
        return None
    if reply.get("ok"):
        return AnswerResult(ok=True, message="answered over the run's control socket")
    error = str(reply.get("error", ""))
    if error == "already answered":
        return AnswerResult(ok=False, message=error)
    return None


async def _run_questions(wf: WorkflowContainer) -> dict | None:
    """The one-shot `questions` round-trip — used only by the answer flow."""
    if wf.native:
        if not wf.runs_volume:
            return None
        try:
            reply = await asyncio.to_thread(
                control.send, wf.runs_volume, control.Request(action=control.QUESTIONS)
            )
        except FileNotFoundError:
            return None
        except control.ControlProtocolError as exc:
            logger.warning("gate one-shot: %s answered unreadably: %s", wf.container_id, exc)
            return None
        return dict(reply) or None
    try:
        reply = await sidecar_hub.ask_questions(wf.container_id)
    except sidecar_hub.SidecarError:
        return None
    if reply.get("error") == "no listener":
        return None
    return reply or None


def _gate_abs_path(wf: WorkflowContainer, gate: GateInfo) -> str:
    """The gate's path on this host, for a consumer that has to open the file."""
    anchor = gate.base or wf.workspace_volume
    if not anchor:
        return gate.file_path
    return str(Path(anchor) / gate.file_path)


async def _answer(wf: WorkflowContainer | None, container_id: str, file_path: str, answer: str) -> AnswerResult:
    """Write an operator's answer into one gate and settle the fleet around it — the state flip, the log, the broadcast."""
    gate = wf.gates.get(file_path) if wf else None
    tel = projection.telemetry_for(wf) if wf else None
    if (gate and gate.kind == "machine") or (
        tel and tel.wait_kind == "machine" and _same_gate(tel.wait_gate_path, file_path)
    ):
        return AnswerResult(ok=False, message="machine waits require their producer's result")
    workspace_volume = (gate.base if gate and gate.base else wf.workspace_volume) if wf else ""
    allow_headerless = bool(gate and gate.legacy_headerless)
    if allow_headerless:
        run = projection.telemetry_for(wf) if wf else None
        allow_headerless = bool(run and run.wait_kind == "operator"
                                and _same_gate(run.wait_gate_path, file_path))
    socket_result = await _answer_via_socket(wf, file_path, answer)
    if socket_result is not None:
        result = socket_result
        if result.ok:
            state.clear_gate(container_id, file_path)
    else:
        answer_path = file_path
        if wf and wf.native and gate and Path(file_path).is_absolute():
            workspace_volume = str(Path(file_path).parent)
            answer_path = Path(file_path).name
        result = await answer_gate(
            container_id,
            answer_path,
            answer,
            workspace_volume=workspace_volume,
            native=bool(wf and wf.native),
            allow_headerless=allow_headerless,
        )
    if result.ok:
        state.clear_gate(container_id, file_path)
    state.record_log(
        {
            "event": "answer",
            "container_id": container_id,
            "file_path": file_path,
            "ok": result.ok,
            "message": result.message,
            "via": "socket" if socket_result is not None else "file",
        }
    )
    if result.ok and wf is not None and not wf.gates and wf.state == WorkflowState.BLOCKED:
        wf.state = WorkflowState.RUNNING

    await _broadcast_shell(container_id)
    if result.ok:
        await state.broadcast(
            {"type": "answered", "id": container_id, "file_path": file_path}
        )
    return result


def _workflow_by_run_id(run_id: str) -> WorkflowContainer | None:
    """A run addressed by run id rather than container id."""
    wf = state.WORKFLOWS.get(run_id)
    if wf is not None:
        return wf
    for candidate in state.WORKFLOWS.values():
        if candidate.run_id == run_id:
            return candidate
    return None


_INBOX_FILE = "inbox.jsonl"


def _docker_inbox_rel_path(runs_volume: str) -> str | None:
    """The volume-relative path to the latest run's inbox file, or ``None`` when the volume has no run directory yet — mirrors how ``discovery._current_run_state`` finds the live run inside a runs volume."""
    dirs = docker_io.list_run_dirs(runs_volume)
    if not dirs:
        return None
    return f"{dirs[-1]}/{_INBOX_FILE}"


def _inbox_messages(wf: WorkflowContainer) -> list[inbox.Message]:
    """Every message in this run's inbox, oldest first — a plain read over :mod:`workhorse.inbox` for a native run, whose ``runs_volume`` is a real host path."""
    if not wf.runs_volume:
        return []
    if wf.native:
        return inbox.all_messages(Path(wf.runs_volume) / _INBOX_FILE)
    rel_path = _docker_inbox_rel_path(wf.runs_volume)
    if rel_path is None:
        return []
    raw = docker_io.read_file(wf.runs_volume, rel_path)
    if not raw:
        return []
    return [inbox.Message.model_validate_json(line) for line in raw.splitlines() if line.strip()]


def _inbox_append(wf: WorkflowContainer, *, message_id: str, body: str, at: str) -> inbox.Message | None:
    """Append one operator message and return it, or ``None`` when the run has no directory yet to append into (a docker run whose first run dir hasn't been created)."""
    if wf.native:
        return inbox.append(Path(wf.runs_volume) / _INBOX_FILE, id=message_id, body=body, at=at)
    rel_path = _docker_inbox_rel_path(wf.runs_volume)
    if rel_path is None:
        return None
    message = inbox.Message.model_validate({"id": message_id, "body": body, "at": at})
    existing = docker_io.read_file(wf.runs_volume, rel_path) or ""
    ok = docker_io.write_file(wf.runs_volume, rel_path, existing + message.model_dump_json() + "\n")
    return message if ok else None


async def _handle_command(data: dict, queue: asyncio.Queue | None = None) -> None:
    cmd = data.get("cmd")
    if cmd == "watch":
        if queue is None:
            return
        run_id = str(data.get("run_id", ""))
        state.watch(queue, run_id)
        if run_id:
            wf = state.WORKFLOWS.get(run_id)
            if wf is not None:
                await state.send(queue, await _detail_message(wf))
        return
    if cmd != "answer":
        return
    container_id = str(data.get("workflow_id", ""))
    file_path = str(data.get("file_path", ""))
    answer = str(data.get("answer", ""))
    wf = state.WORKFLOWS.get(container_id)
    await _answer(wf, container_id, file_path, answer)


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
    """One socket per open tab, carrying JSON in both directions: fleet-wide ``state``/``notify``/``answered`` frames plus this tab's own ``detail`` frames down, ``{"cmd": "answer"|"watch", ...}`` up."""
    await socket.accept()
    queue: asyncio.Queue = asyncio.Queue()
    state.add_client(queue)
    try:
        await socket.send_text(json.dumps(projection.state_message(_all_workflows())))
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


async def _apply_hello(container_id: str, data: dict) -> None:
    """Fold a sidecar's on-connect ``hello`` into the fleet."""
    identity = data.get("identity") or {}
    snapshot = data.get("snapshot") or {}
    await _ensure_volumes(container_id)
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
    await _broadcast_shell(container_id)


async def _apply_socket_progress(container_id: str, data: dict) -> None:
    state.upsert_workflow(container_id, current_node=data.get("current_node"), state=WorkflowState.RUNNING)
    await _broadcast_shell(container_id)


def _apply_socket_turn(conn: sidecar_hub.SidecarConnection, data: dict) -> None:
    """A container says one of its turn records moved; go and fetch it."""
    sidecar_turns.schedule(
        conn,
        run=str(data.get("run", "")),
        run_id=str(data.get("run_id", "")),
        workflow=str(data.get("workflow", "")),
    )


async def _apply_socket_blocked(container_id: str, data: dict) -> None:
    file_path = str(data.get("file_path", ""))
    if not file_path:
        return
    question = str(data.get("question", ""))
    wf = state.upsert_workflow(container_id, state=WorkflowState.BLOCKED)
    wf.gates[file_path] = GateInfo(workflow_id=container_id, file_path=file_path, question=question)
    await _broadcast_shell(container_id)
    await _broadcast_notify(f"{wf.name}: {question[:_QUESTION_NOTIFY_LIMIT]}")
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
    except WebSocketDisconnect:
        pass
    finally:
        if conn is not None:
            sidecar_hub.unregister(conn)


@post("/reload", include_in_schema=False)
async def reload(container_id: Annotated[str, QueryParameter()] = "") -> dict:
    """Broadcast a ``reload`` to connected sidecars (all, or one when ``container_id`` is given)."""
    targets = [container_id] if container_id else sidecar_hub.connected_ids()
    reloaded = 0
    for cid in targets:
        conn = sidecar_hub.get(cid)
        if conn is None:
            continue
        try:
            await conn.send_reload()
            reloaded += 1
        except Exception:  # noqa: BLE001 - a dead socket just means nothing to reload there
            pass
    return {"ok": True, "reloaded": reloaded}


_scan_task: asyncio.Task | None = None
_rules_task: asyncio.Task | None = None
_live_task: asyncio.Task | None = None
_archive_task: asyncio.Task | None = None


async def _rules_loop() -> None:
    """Periodic evaluation of the time-based alert rules, plus the two housekeeping passes that bound groom's memory over a long serve: evicting finished/dead runs from the hot cache, and re-pruning the durable store on its own slower clock."""
    last_prune = time.monotonic() - PRUNE_EVERY_S
    last_harvest = time.monotonic()
    while True:
        await asyncio.sleep(RULES_TICK_S)
        try:
            now = time.time()
            await _dispatch_alerts(alerts.check_time_rules(now))
            state.evict_runs(alerts.stale_run_ids(now))
            if time.monotonic() - last_harvest >= HARVEST_EVERY_S:
                await asyncio.to_thread(turns.harvest)
                last_harvest = time.monotonic()
            if time.monotonic() - last_prune >= PRUNE_EVERY_S:
                archived = await asyncio.to_thread(archive.archived_run_ids)
                await asyncio.to_thread(store.prune, store.RETENTION_DAYS, None, archived)
                last_prune = time.monotonic()
        except Exception:  # noqa: BLE001
            pass


async def _backfill_wait_gate(run: RunTelemetry) -> None:
    """Fetch the live question over the control socket when telemetry's copy of gate_path/gate_question is missing."""
    if not run.native or not run.run_dir:
        return
    try:
        reply = await asyncio.to_thread(
            control.send, run.run_dir, control.Request(action=control.QUESTIONS)
        )
    except FileNotFoundError:
        return
    except control.ControlProtocolError as exc:
        logger.warning("gate backfill: %s answered unreadably: %s", run.run_id, exc)
        return
    if not reply.get("ok"):
        return
    raw_questions = reply.get("questions")
    questions = [q for q in raw_questions if isinstance(q, dict)] if isinstance(raw_questions, list) else []
    if not questions:
        return
    question = questions[0]
    run.wait_gate_path = str(question.get("path", ""))
    run.wait_gate_question = str(question.get("question", ""))


async def _live_loop() -> None:
    """Re-render the run list on a clock and push it to every open dashboard."""
    while True:
        await asyncio.sleep(LIVE_TICK_S)
        if not state.CLIENTS:
            continue
        try:
            died: list[alerts.Alert] = []
            runs = list(state.RUNS.values())
            incomplete = [
                run
                for run in runs
                if run.wait_kind in ("operator", "machine") and not run.wait_gate_path
            ]
            if incomplete:
                await asyncio.gather(*(_backfill_wait_gate(run) for run in incomplete))
            for run in runs:
                _sync_native_row(run, died)
            await _dispatch_alerts(died)
            await _broadcast_shell()
            await _push_watched()
        except Exception:  # noqa: BLE001
            pass


async def _spawn_live() -> None:
    """on_startup hook: start the clock that keeps time-derived row state honest."""
    global _live_task
    _live_task = asyncio.create_task(_live_loop())


async def _stop_live() -> None:
    if _live_task is not None:
        _live_task.cancel()


async def _archive_loop() -> None:
    """Write expired runs out to disk on a slow clock, forever."""
    last = time.monotonic() - ARCHIVE_EVERY_S
    while True:
        await asyncio.sleep(RULES_TICK_S)
        if time.monotonic() - last < ARCHIVE_EVERY_S:
            continue
        last = time.monotonic()
        try:
            result = await asyncio.to_thread(archive.sweep)
            if result.archived or result.failed:
                logger.info(
                    "groom: archived %d run(s), %d row(s), %d byte(s); %d failed,"
                    " %d still pending",
                    len(result.archived), result.rows, result.bytes,
                    len(result.failed), result.pending,
                )
        except Exception:  # noqa: BLE001
            logger.warning("groom: archival sweep failed", exc_info=True)


async def _spawn_archive() -> None:
    """on_startup hook: start the archival ticker."""
    global _archive_task
    _archive_task = asyncio.create_task(_archive_loop())


async def _stop_archive() -> None:
    if _archive_task is not None:
        _archive_task.cancel()


async def _spawn_rules() -> None:
    """on_startup hook: start the alert-rule ticker, and nothing else."""
    global _rules_task
    _rules_task = asyncio.create_task(_rules_loop())


async def _stop_rules() -> None:
    if _rules_task is not None:
        _rules_task.cancel()


async def _background_scan() -> None:
    """The startup discovery pass, run off the event loop *after* the server is already accepting connections."""
    try:
        await _reconcile()
    finally:
        state.SCANNING = False
        await _broadcast_shell()


async def _recover_attend() -> None:
    """on_startup hook: restart the attendants this groom was holding when it died."""
    try:
        restarted = await asyncio.to_thread(attend.recover_orphans)
    except Exception:
        logger.exception("attend: boot recovery failed")
        return
    if restarted:
        logger.info("attend: restarted %d attendant(s) left running by a dead groom", restarted)


async def _recover_dispatch() -> None:
    """on_startup hook: mark every `running` dispatch row dead pids own as `failed`."""
    try:
        closed = await asyncio.to_thread(dispatch.recover_orphans)
    except Exception:
        logger.exception("dispatch: boot recovery failed")
        return
    if closed:
        logger.info("dispatch: marked %d orphaned item(s) failed after a dead groom", closed)


async def _spawn_scan() -> None:
    """on_startup hook: only *schedule* discovery and return immediately, so uvicorn finishes lifespan-startup and binds the port right away instead of blocking on the whole docker scan (the old _startup_scan did the latter)."""
    global _scan_task
    _scan_task = asyncio.create_task(_background_scan())


def create_app() -> Litestar:
    return Litestar(
        route_handlers=[
            index,
            api_state,
            repos,
            files,
            file_content,
            worker_detail,
            diff,
            outbox_get,
            outbox_post,
            inbox_get,
            inbox_post,
            refresh,
            push_progress,
            attend_queue,
            attend_sessions,
            attend_session,
            attend_stop,
            attend_settings_get,
            attend_settings_post,
            dispatch_queues,
            dispatch_enqueue,
            dispatch_items,
            dispatch_delete,
            dispatch_stop,
            push_blocked,
            push_exited,
            otlp_traces,
            otlp_metrics,
            otlp_logs,
            api_live,
            dashboard_ws,
            dashboard_sidecar,
            reload,
            create_static_files_router(path="/assets", directories=[ASSETS_DIR]),
        ],
        on_startup=[
            _spawn_scan,
            _spawn_rules,
            _spawn_live,
            _spawn_archive,
            _recover_attend,
            _recover_dispatch,
        ],
        on_shutdown=[_stop_rules, _stop_live, _stop_archive, pools.shutdown_all],
    )
