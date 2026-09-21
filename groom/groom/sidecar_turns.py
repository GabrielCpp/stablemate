"""Pulling a container's turn records across the sidecar socket into the archive."""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from groom import turns

logger = logging.getLogger(__name__)

MAX_PULL_BYTES = int(os.environ.get("GROOM_TURN_PULL_MAX_BYTES", str(256 * 1024 * 1024)))

RPC_TIMEOUT = 30.0

STAGING_DIR = ".incoming"

_IN_FLIGHT: dict[str, dict[str, bool]] = {}


def staging_root() -> Path:
    return turns.transcripts_root() / STAGING_DIR


def _staged(container_id: str, run: str) -> Path:
    return staging_root() / container_id / (run or "run")


async def _fetch_file(conn: Any, run: str, rel: str, target: Path) -> int:
    """Copy one remote file into ``target``, chunk by chunk; bytes written."""
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    written = 0
    with partial.open("wb") as fh:
        while True:
            reply = await conn.rpc(
                "readTurnFile",
                {"run": run, "path": rel, "offset": written},
                timeout=RPC_TIMEOUT,
            )
            chunk = base64.b64decode(str((reply or {}).get("data", "")))
            fh.write(chunk)
            written += len(chunk)
            if (reply or {}).get("eof") or not chunk:
                break
            if written >= MAX_PULL_BYTES:
                break
    partial.replace(target)
    return written


async def pull(conn: Any, *, run: str = "", run_id: str = "", workflow: str = "") -> int:
    """Mirror one container run's turn-record surface and archive it; records archived."""
    listing = await conn.rpc("listTurns", {"run": run}, timeout=RPC_TIMEOUT)
    if not isinstance(listing, dict):
        return 0
    remote_run = str(listing.get("run", "") or run)
    stage = _staged(conn.container_id, remote_run)
    budget = MAX_PULL_BYTES
    for entry in listing.get("files") or []:
        rel = str((entry or {}).get("path", ""))
        if not rel or rel.startswith("/") or ".." in rel.split("/"):
            continue
        size = int((entry or {}).get("size", 0))
        target = stage / rel
        if target.is_file() and target.stat().st_size == size:
            continue
        if budget <= 0:
            logger.debug("turn pull budget exhausted for %s", conn.container_id)
            break
        budget -= await _fetch_file(conn, remote_run, rel, target)
    return await asyncio.to_thread(turns.harvest_run, stage, run_id, workflow)


async def _pull_until_quiet(conn: Any, run: str, run_id: str, workflow: str) -> None:
    container = conn.container_id
    flags = _IN_FLIGHT[container]
    try:
        while True:
            await pull(conn, run=run, run_id=run_id, workflow=workflow)
            if not flags["again"]:
                return
            flags["again"] = False
    except Exception:  # noqa: BLE001 - a container whose records did not arrive is not a broken groom
        logger.debug("turn pull failed for %s", container, exc_info=True)
    finally:
        try:
            if flags["final"]:
                await asyncio.to_thread(shutil.rmtree, staging_root() / container, True)
        finally:
            _IN_FLIGHT.pop(container, None)


def schedule(
    conn: Any,
    *,
    run: str = "",
    run_id: str = "",
    workflow: str = "",
    final: bool = False,
) -> None:
    """Ask for a pull without waiting for it."""
    container = conn.container_id
    flags = _IN_FLIGHT.get(container)
    if flags is not None:
        flags["again"] = True
        flags["final"] = flags["final"] or final
        return
    _IN_FLIGHT[container] = {"again": False, "final": final}
    task = asyncio.create_task(_pull_until_quiet(conn, run, run_id, workflow))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)


_TASKS: set[asyncio.Task] = set()
