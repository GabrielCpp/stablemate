from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from litestar import get, post
from litestar.exceptions import (
    ClientException,
    HTTPException,
    NotFoundException,
    ServiceUnavailableException,
)
from litestar.params import PathParameter, QueryParameter

from groom import (
    activity,
    alerts,
    archive,
    banner,
    docker_io,
    history,
    live,
    localfs,
    overview,
    pools,
    projection,
    records,
    state,
)
from groom.gates import extract_question
from groom.native import _tail_transcript
from groom.routes.gates import _workflow_by_run_id
from groom.summaries import _wake_summaries


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


def _overview_with_ending(run_id: str) -> dict:
    return {**overview.run_overview(run_id), "ending": banner.banner(run_id)}


@get("/api/run/{run_id:str}/overview", include_in_schema=False)
async def run_overview(run_id: Annotated[str, PathParameter()]) -> dict:
    """One run's cost so far and its time per flow, from the queries behind ``groom cost`` and ``groom profile``."""
    return await pools.QUERY.run(_overview_with_ending, run_id)


def _archived(run_id: str) -> tuple[dict | None, Path | None]:
    """The stored row of an archived run and the folder holding its archive under its exact id. The row is None when the run is not an archive, and the folder is None when the archive's files are gone."""
    row = history.stored(run_id)
    if row is None or not row["archived"]:
        return None, None
    return row, archive.exact_dir(run_id)


def _archive_overview(run_id: str) -> dict | None:
    """An archived run's Overview, read from its frozen archive, or from its stored summary when the archive's files are gone. None when the run is not an archive. The run is resolved by exact id before anything is read, because ``run_source`` falls back to the live store and ``archive_dir`` to a prefix."""
    row, folder = _archived(run_id)
    if row is None:
        return None
    if folder is None:
        return overview.stored_overview(row, history.comparison(run_id))
    with archive.dropping_an_unreadable_index(folder):
        found = _overview_with_ending(run_id)
    if found["ending"]:
        found["ending"]["moment"] = ""
    return {**found, "archive": "ready"}


@get("/api/archive/{run_id:str}/overview", include_in_schema=False)
async def archive_overview(run_id: Annotated[str, PathParameter()]) -> dict:
    """One archived run's Overview, on its own pool so that reading an archive never holds the dashboard's queries."""
    found = await pools.ARCHIVE.run(_archive_overview, run_id)
    if found is None:
        raise NotFoundException(f"no archived run {run_id}")
    return found


@get("/api/history", include_in_schema=False)
async def api_history(archives: Annotated[int, QueryParameter()] = 0) -> dict:
    """The runs that ended in the retention window, newest first, with the totals above the table, or every summary there is with ``archives=1``. Reads the stored summaries and nothing else, and asks the worker to give any archive without a row one."""
    found = await pools.QUERY.run(history.listing, alerts.unfinished_run_ids(), None, bool(archives))
    if found["unlisted"]:
        _wake_summaries()
    return found


@post("/api/history/{run_id:str}/retry", include_in_schema=False)
async def history_retry(run_id: Annotated[str, PathParameter()]) -> dict:
    """Ask for an archive whose summary could not be read to be read again."""
    asked = await asyncio.to_thread(history.retry, run_id)
    if asked:
        live.bump("history")
        _wake_summaries()
    return {"ok": asked}


async def _live_turns(run_id: str) -> activity.LiveRows:
    """The watched run's live transcript rows by turn slug, brought up to date first when the run is native."""
    wf = _workflow_by_run_id(run_id)
    if wf is not None and wf.native:
        await _tail_transcript(wf)
    history = state.HISTORIES.get(run_id)
    if history is None:
        return {}
    async with state.HISTORY_LOCK:
        rows = list(history.transcript)
    live: activity.LiveRows = {}
    for row in rows:
        live.setdefault(str(row["slug"]), []).append(row)
    return live


def _standing(run_id: str) -> dict | None:
    """Where a live run is now: its current step, or the operator gate it waits at."""
    wf = _workflow_by_run_id(run_id)
    if wf is None:
        return None
    tel = projection.telemetry_for(wf)
    here = projection.running_node(wf, tel)
    if here is None or tel is None:
        return None
    gate = next(iter(projection.reported_gates(wf, tel)), None)
    return {
        "node": here["node"],
        "since_ts": here["since_ts"],
        "wait_kind": here["wait_kind"],
        "turn_active": tel.turn_active,
        "path": gate.file_path if gate else "",
        "question": extract_question(gate.question) if gate and gate.question else "",
    }


def _gate_reader(run_id: str):
    """A reader of one gate file in the run's workspace, or none when the run keeps no workspace groom can read."""
    wf = _workflow_by_run_id(run_id)
    if wf is None or not wf.workspace_volume:
        return lambda _path: None
    read = localfs.read_file if wf.native else docker_io.read_file
    volume = wf.workspace_volume
    return lambda path: read(volume, path)


def _archive_read(run_id: str, read: Callable, *args):
    """``read(*args)`` over one archived run's frozen file. The run is resolved by exact id before anything is read, and ``run_source`` is entered here because the pool does not copy the context variable that redirects the reads."""
    row, folder = _archived(run_id)
    if row is None:
        raise NotFoundException(f"no archived run {run_id}")
    if folder is None:
        raise HTTPException(status_code=410, detail="this archive's files are gone")
    with archive.dropping_an_unreadable_index(folder), archive.run_source(run_id):
        return read(*args)


def _in_archive(run_id: str) -> Callable:
    async def read(fn: Callable, *args):
        return await pools.ARCHIVE.run(_archive_read, run_id, fn, *args)

    return read


async def _timeline(read: Callable, run_id: str, live: activity.LiveRows, standing: dict | None, logs: int) -> dict:
    return await read(activity.timeline, run_id, live, standing, bool(logs))


async def _records(read: Callable, run_id: str, before: str, limit: int, metrics: int) -> dict:
    try:
        return await read(records.page, run_id, before, limit, bool(metrics))
    except records.BadCursor as exc:
        raise ClientException(detail="not a cursor of this run's records") from exc


async def _search(read: Callable, run_id: str, q: str, live: activity.LiveRows, pending: bool) -> dict:
    try:
        return await read(activity.search, run_id, q, live, pending)
    except activity.SearchFailed as exc:
        raise ServiceUnavailableException(detail="the transcripts could not be searched") from exc


async def _entry(read: Callable, run_id: str, key: str, *rest) -> dict:
    try:
        return await read(activity.entry, run_id, key, *rest)
    except activity.EntryNotFound as exc:
        raise NotFoundException(detail="no such step or gate") from exc


async def _turn(read: Callable, run_id: str, slug: str, live: activity.LiveRows, pending: bool) -> dict:
    try:
        return await read(activity.turn, run_id, slug, live, pending)
    except activity.TurnNotFound as exc:
        raise NotFoundException(detail="no such turn") from exc
    except activity.TurnUnreadable as exc:
        raise ServiceUnavailableException(detail="the turn could not be read") from exc


@get("/api/run/{run_id:str}/activity", include_in_schema=False)
async def run_activity(run_id: Annotated[str, PathParameter()], logs: Annotated[int, QueryParameter()] = 0) -> dict:
    """One run's agent turns, oldest first, with the one still running read from its live transcript. `logs=1` adds the run's info logs at their place in the timeline."""
    return await _timeline(pools.QUERY.run, run_id, await _live_turns(run_id), _standing(run_id), logs)


@get("/api/archive/{run_id:str}/activity", include_in_schema=False)
async def archive_activity(run_id: Annotated[str, PathParameter()], logs: Annotated[int, QueryParameter()] = 0) -> dict:
    """One archived run's turns, read from its frozen file on the archive pool."""
    return await _timeline(_in_archive(run_id), run_id, {}, None, logs)
