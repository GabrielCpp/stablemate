from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Literal

from litestar import Response, get
from litestar.enums import MediaType
from litestar.params import PathParameter, QueryParameter

from groom import (
    docker_io,
    gitdiff,
    live,
    localfs,
    pools,
    projection,
    sidecar_hub,
    state,
)
from groom.models import (
    WorkflowContainer,
)
from groom.native import (
    SERVED_BY_HOST,
    SERVED_BY_SIDECAR,
    SERVED_BY_VOLUME,
    _all_workflows,
    _queue_norms,
    _run_facts,
    _stamp_revisions,
)
from groom.native_attend import _gate_abs_path

logger = logging.getLogger(__name__)


ASSETS_DIR = Path(__file__).parent.parent / "assets"


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
    (Path(__file__).parent.parent / "templates" / "dashboard.html").read_bytes()
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


def _checkout_names(served: dict) -> dict:
    """The checkouts a sidecar reports beside a read, or nothing when it is too old to name them."""
    return {"repos": [str(name) for name in served["repos"]]} if isinstance(served.get("repos"), list) else {}


def _branch_start(served: dict) -> dict:
    """Where a sidecar says the branch started, or ``based: False`` when it is too old to say."""
    if not isinstance(served.get("base_reason"), str):
        return {"based": False}
    return {
        "based": True,
        "base": str(served.get("base") or ""),
        "base_ref": str(served.get("base_ref") or ""),
        "base_branch": str(served.get("base_branch") or ""),
        "base_reason": served["base_reason"],
    }


@get("/files/{container_id:str}", include_in_schema=False)
async def files(
    container_id: Annotated[str, PathParameter()],
    repo: Annotated[str, QueryParameter()] = "",
) -> dict:
    """The repo-relative file paths of one checkout, whether the read failed, and whether the source reports failures, as ``{"paths", "failed", "reported", "served"}``, plus ``"repos"`` when the sidecar names the run's checkouts."""
    served = await _sidecar_rpc(container_id, "getTree", {"repo": repo})
    if served is not None:
        return {
            "paths": list(served.get("paths") or []),
            "failed": bool(served.get("failed")),
            "reported": "failed" in served,
            "served": SERVED_BY_SIDECAR,
            **_checkout_names(served),
        }

    wf = state.WORKFLOWS.get(container_id)
    volume = wf.workspace_volume if wf else ""
    if not volume:
        return {"paths": [], "failed": True, "reported": True, "served": SERVED_BY_VOLUME}
    native = bool(wf and wf.native)
    reader = localfs.read_tree if native else docker_io.read_tree
    read = await asyncio.to_thread(reader, volume, repo)
    return {"paths": list(read["paths"]), "failed": read["failed"], "reported": True, "served": SERVED_BY_HOST if native else SERVED_BY_VOLUME}


@get("/file/{container_id:str}", include_in_schema=False)
async def file_content(
    container_id: Annotated[str, PathParameter()],
    repo: Annotated[str, QueryParameter()] = "",
    path: Annotated[str, QueryParameter()] = "",
) -> dict:
    """One file's text, the highlight.js language its name implies, whether the read failed, and whether the source reports failures, as ``{"path", "content", "lang", "failed", "reported", "served"}``. ``served`` is ``"sidecar"`` when the run's sidecar answered and ``"volume"`` for every fallback reader, so a client can tell a live answer from a stand-in."""
    lang = projection.file_lang(path)
    served = await _sidecar_rpc(container_id, "getFile", {"repo": repo, "path": path})
    if served is not None:
        return {
            "path": path,
            "content": served.get("content") or "",
            "lang": lang,
            "failed": bool(served.get("failed")),
            "reported": "failed" in served,
            "served": SERVED_BY_SIDECAR,
        }

    def unread() -> dict:
        return {"path": path, "content": "", "lang": lang, "failed": True, "reported": True, "served": SERVED_BY_VOLUME}

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
        return unread()
    reader = localfs.read_file if wf and wf.native else docker_io.read_file
    try:
        text = await asyncio.to_thread(reader, volume, rel)
    except ValueError:
        return unread()
    if text is None:
        return unread()
    served_by = SERVED_BY_HOST if wf and wf.native else SERVED_BY_VOLUME
    return {"path": path, "content": text, "lang": lang, "failed": False, "reported": True, "served": served_by}


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
            live.mark_run(cid)


@get("/worker/{container_id:str}", include_in_schema=False)
async def worker_detail(container_id: Annotated[str, PathParameter()]) -> dict:
    """One run's detail pane as JSON — activity, its gates, live metrics, log trail."""
    wf = state.WORKFLOWS.get(container_id)
    if wf is None:
        return {"found": False, "id": container_id}
    tel, facts, logs, history = await _run_facts(wf)
    _queue_norms(wf, tel)
    detail = projection.run_detail(wf, tel, facts, logs, history=history)
    _stamp_revisions(detail, wf)
    return detail


@get("/diff/{container_id:str}", include_in_schema=False)
async def diff(
    container_id: Annotated[str, PathParameter()],
    repo: Annotated[str, QueryParameter()] = "",
    view: Annotated[str, QueryParameter()] = "",
) -> dict:
    """One checkout's uncommitted change: the diff, the untracked files, whether the read failed, and whether the source reports failures, and ``"served"`` saying whether the sidecar or a fallback reader answered, plus ``"repos"`` when the sidecar names the run's checkouts. ``?view=branch`` reads the change since the branch started instead, with the base the sidecar computed and ``"based"`` saying whether it reported one."""
    branch = view == gitdiff.VIEW_BRANCH
    served = await _sidecar_rpc(container_id, "getDiff", {"repo": repo, **({"view": view} if branch else {})})
    if served is not None:
        return {
            "diff": served.get("diff") or "",
            "untracked": list(served.get("untracked") or []),
            "failed": bool(served.get("failed")),
            "reported": "failed" in served,
            "served": SERVED_BY_SIDECAR,
            **(_branch_start(served) if branch else {}),
            **_checkout_names(served),
        }

    wf = state.WORKFLOWS.get(container_id)
    volume = wf.workspace_volume if wf else ""
    if wf and wf.native and volume:
        if branch:
            read_branch = await asyncio.to_thread(localfs.read_branch_diff, volume, repo)
            return {**read_branch, "based": True, "reported": True, "served": SERVED_BY_HOST}
        read = await asyncio.to_thread(localfs.read_diff, volume, repo)
        return {**read, "reported": True, "served": SERVED_BY_HOST}
    if not volume or branch:
        return {**gitdiff.unreadable(), "reported": True, "served": SERVED_BY_VOLUME}
    read = await asyncio.to_thread(docker_io.read_diff, volume, repo)
    return {**read, "reported": True, "served": SERVED_BY_VOLUME}
