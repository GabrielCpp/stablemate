from __future__ import annotations

import asyncio
from typing import Annotated

from litestar import Response, delete, get, post
from litestar.params import PathParameter

from groom import (
    attend,
    attend_ledger,
    attend_transcript,
    dispatch,
    dispatch_ledger,
    live,
)
from groom.settings import AttendSettings, write_attend_settings


@get("/api/attend/queue", include_in_schema=False)
async def attend_queue() -> dict:
    """Every run currently waiting on an attendant, oldest first — the whole fleet."""
    return {"mode": attend.mode(), "jobs": attend.queue()}


@get("/api/attend/sessions", include_in_schema=False)
async def attend_sessions() -> dict:
    """The attendance log: the latest 200, newest first."""
    rows = await asyncio.to_thread(attend_ledger.attend_recent, 200)
    return {"mode": attend.mode(), "sessions": rows}


@get("/api/attend/sessions/{session_id:str}", include_in_schema=False)
async def attend_session(session_id: Annotated[str, PathParameter()]) -> dict:
    """One attendance, rendered as a conversation — not as JSON."""
    row = await asyncio.to_thread(attend_ledger.attend_by_session, session_id)
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
    live.mark_fleet()
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
    updated = AttendSettings(
        mode=wanted,
        last_mode=current.last_mode if wanted == attend.OFF else wanted,
        cli=current.cli,
        deny=current.deny,
    )
    await asyncio.to_thread(write_attend_settings, updated)
    live.mark_fleet()
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
    live.mark_fleet()
    return Response(content={"ok": True, "item": item})


@get("/api/dispatch/{queue:str}/items", include_in_schema=False)
async def dispatch_items(queue: Annotated[str, PathParameter()]) -> dict:
    """This queue's items, newest first — the latest 200, same cap `attend_sessions` uses."""
    rows = await asyncio.to_thread(dispatch_ledger.dispatch_list, queue, 200)
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
    live.mark_fleet()
    return {"ok": stopped}
