from __future__ import annotations

from typing import Annotated

from litestar import get
from litestar.params import PathParameter, QueryParameter

from groom import (
    pools,
    records,
    state,
)
from groom.routes.runs import (
    _entry,
    _gate_reader,
    _in_archive,
    _live_turns,
    _records,
    _search,
    _standing,
    _turn,
)

_RunId = Annotated[str, PathParameter()]


_Cursor = Annotated[str, QueryParameter()]


_PageSize = Annotated[int, QueryParameter()]


_Switch = Annotated[int, QueryParameter()]


@get("/api/run/{run_id:str}/records", include_in_schema=False)
async def run_records(run_id: _RunId, before: _Cursor = "", limit: _PageSize = records.PAGE, metrics: _Switch = 0) -> dict:
    """One page of the run's stored records, newest first, from the cursor a previous page returned."""
    return await _records(pools.QUERY.run, run_id, before, limit, metrics)


@get("/api/archive/{run_id:str}/records", include_in_schema=False)
async def archive_records(run_id: _RunId, before: _Cursor = "", limit: _PageSize = records.PAGE, metrics: _Switch = 0) -> dict:
    """One page of an archived run's stored records, newest first, read from its frozen file."""
    return await _records(_in_archive(run_id), run_id, before, limit, metrics)


@get("/api/run/{run_id:str}/search", include_in_schema=False)
async def run_search(run_id: Annotated[str, PathParameter()], q: Annotated[str, QueryParameter()] = "") -> dict:
    """The turns of this one run whose transcript says the query, each with its first matching line."""
    wf = state.WORKFLOWS.get(run_id)
    return await _search(pools.QUERY.run, run_id, q, await _live_turns(run_id), wf is not None and not wf.native)


@get("/api/archive/{run_id:str}/search", include_in_schema=False)
async def archive_search(run_id: Annotated[str, PathParameter()], q: Annotated[str, QueryParameter()] = "") -> dict:
    """The turns of one archived run whose transcript says the query."""
    return await _search(_in_archive(run_id), run_id, q, {}, False)


@get("/api/run/{run_id:str}/entry/{key:str}", include_in_schema=False)
async def run_entry(
    run_id: Annotated[str, PathParameter()], key: Annotated[str, PathParameter()]
) -> dict:
    """One step, operator gate, backend retry or churn alert of the run, read in full."""
    return await _entry(pools.QUERY.run, run_id, key, await _live_turns(run_id), _standing(run_id), _gate_reader(run_id))


@get("/api/archive/{run_id:str}/entry/{key:str}", include_in_schema=False)
async def archive_entry(
    run_id: Annotated[str, PathParameter()], key: Annotated[str, PathParameter()]
) -> dict:
    """One step, gate, backend retry or churn alert of an archived run, read in full. Its workspace is gone, so a gate's answer reads as unavailable."""
    return await _entry(_in_archive(run_id), run_id, key, {}, None, lambda _path: None)


@get("/api/run/{run_id:str}/activity/{slug:str}", include_in_schema=False)
async def run_turn(
    run_id: Annotated[str, PathParameter()], slug: Annotated[str, PathParameter()]
) -> dict:
    """One agent turn: its head figures, its messages and its tool calls."""
    wf = state.WORKFLOWS.get(run_id)
    return await _turn(pools.QUERY.run, run_id, slug, await _live_turns(run_id), wf is not None and not wf.native)


@get("/api/archive/{run_id:str}/activity/{slug:str}", include_in_schema=False)
async def archive_turn(
    run_id: Annotated[str, PathParameter()], slug: Annotated[str, PathParameter()]
) -> dict:
    """One agent turn of an archived run, read from the records the archive kept."""
    return await _turn(_in_archive(run_id), run_id, slug, {}, False)
