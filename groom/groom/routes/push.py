from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Annotated

from litestar import get, post
from litestar.params import PathParameter, QueryParameter

from groom import (
    alerting,
    attend,
    live,
    native,
    run_inbox,
    state,
)
from groom.alerting import _NOT_A_DEATH_EXIT, _QUESTION_NOTIFY_LIMIT
from groom.models import (
    GateInfo,
    WorkflowContainer,
    WorkflowState,
)
from groom.native_attend import _attend_gates
from groom.routes.gates import _answer, _workflow_by_run_id


async def _push_row(data: dict, **fields: object) -> tuple[str, WorkflowContainer | None]:
    """The row a push names, made or updated: keyed by its container id, else its run id. A native row keeps the identity its telemetry gave it."""
    key = state.row_key(data)
    if not key:
        return "", None
    containerless = not data.get("container_id")
    if not containerless:
        await native._ensure_volumes(key)
    existing = state.WORKFLOWS.get(key)
    if existing is not None and existing.native:
        return key, state.upsert_workflow(key, **fields)
    wf = state.upsert_workflow(
        key,
        name=data.get("name"),
        repo_name=data.get("repo_name"),
        repo_branch=data.get("repo_branch"),
        run_id=key if containerless else None,
        containerless=containerless,
        **fields,
    )
    return key, wf


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
    messages = await asyncio.to_thread(run_inbox.messages, wf)
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
    message = await asyncio.to_thread(run_inbox.append, wf, message_id=message_id, body=body, at=at)
    if message is None:
        return {"ok": False, "message": "no run directory yet"}
    return {"ok": True, "message": message.model_dump()}


@post("/refresh", include_in_schema=False)
async def refresh() -> dict:
    """Re-run the reconciliation scan on demand (e.g."""
    state.SCANNING = True
    live.mark_fleet()
    try:
        count = await native._reconcile()
    finally:
        state.SCANNING = False
    live.mark_fleet()
    return {"ok": True, "count": count}


@post("/push/progress", include_in_schema=False)
async def push_progress(data: dict) -> dict:
    container_id, wf = await _push_row(data, current_node=data.get("current_node"), state=WorkflowState.RUNNING)
    if wf is None:
        return {"ok": False}
    live.mark_fleet()
    live.mark_run(container_id)
    return {"ok": True}


@post("/push/blocked", include_in_schema=False)
async def push_blocked(data: dict) -> dict:
    """Used both by groom-sidecar and by the await_operator.py backstop push — same shape, same handling, whichever gets there first (or both; the second call is just a harmless re-render)."""
    file_path = str(data.get("file_path", ""))
    if not file_path:
        return {"ok": False}
    container_id, wf = await _push_row(data, state=WorkflowState.BLOCKED)
    if wf is None:
        return {"ok": False}
    question = str(data.get("question", ""))
    wf.gates[file_path] = GateInfo(workflow_id=container_id, file_path=file_path, question=question)

    live.mark_fleet()
    live.mark_run(container_id)
    await alerting._broadcast_notify(f"{wf.name}: {question[:_QUESTION_NOTIFY_LIMIT]}")
    gate = next(iter(wf.gates.values()))
    _attend_gates(wf, [gate])
    return {"ok": True}


@post("/push/exited", include_in_schema=False)
async def push_exited(data: dict) -> dict:
    """The workflow process ended (fired once by the container entrypoint via ``groom-sidecar --exit-code``)."""
    exit_code = data.get("exit_code")
    container_id, wf = await _push_row(
        data,
        state=WorkflowState.FINISHED,
        exit_code=int(exit_code) if isinstance(exit_code, (int, str)) and str(exit_code).lstrip("-").isdigit() else None,
    )
    if wf is None:
        return {"ok": False}
    wf.gates.clear()
    attend.release(container_id)
    if wf.exit_code is not None and wf.exit_code not in _NOT_A_DEATH_EXIT:
        alerting._attend_death(container_id)
    live.mark_fleet()
    live.mark_run(container_id)
    return {"ok": True}
