"""Pulling a container's turn records across the sidecar socket into the archive.

A run inside a container writes its turn records to a run dir the host cannot read:
the volume is the container's, and the container is thrown away when the run ends. So
the evidence that explains a livelock is destroyed by the same event that makes anyone
want it. This module is the transport that gets it out — the container announces, the
host pulls, and what lands is a faithful mirror of the run dir under a staging tree,
which :func:`groom.turns.harvest_run` then archives exactly as if the run had been
local.

Mirror-then-harvest rather than a second ingest path on purpose: the archive's rules —
the visit key, the digest, what counts as a record — are stated once, in
:mod:`groom.turns`, and a container's records get them by construction rather than by a
parallel implementation that has to be kept in agreement.

The staging tree is a cache, not a second archive. It keeps the bytes already fetched so
a re-pull asks only for the files whose length moved, and deleting it costs one slow
pull and nothing else.

The sidecar stays **non-authoritative**: if it never connects, or the pull fails
halfway, that container's records are simply absent from the archive. Nothing here may
raise into the socket loop.
"""

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

#: Ceiling on one pull. A run dir grows without bound over a long run; this bounds what
#: a single pass will move, and the next announce moves the rest.
MAX_PULL_BYTES = int(os.environ.get("GROOM_TURN_PULL_MAX_BYTES", str(256 * 1024 * 1024)))

#: Per-RPC deadline. Generous next to the panel reads' 5s: a chunk read competes with a
#: container that is busy running an agent, and a slow answer is better than a lost file.
RPC_TIMEOUT = 30.0

#: Where fetched run dirs are mirrored, under the archive root so one setting moves both.
STAGING_DIR = ".incoming"

#: Announces arrive per watch batch; pulls are whole-run and idempotent. One in flight
#: per container, with a single re-run queued behind it, collapses a burst into two
#: passes instead of one per frame. ``again`` is that queued re-run; ``final`` records
#: that a terminal arrived while a pull was already running, so it is not lost.
_IN_FLIGHT: dict[str, dict[str, bool]] = {}


def staging_root() -> Path:
    return turns.transcripts_root() / STAGING_DIR


def _staged(container_id: str, run: str) -> Path:
    return staging_root() / container_id / (run or "run")


async def _fetch_file(conn: Any, run: str, rel: str, target: Path) -> int:
    """Copy one remote file into ``target``, chunk by chunk; bytes written.

    Written to a ``.part`` and moved into place, so an interrupted pull cannot leave a
    half-file that the next harvest would digest and archive as though it were the whole
    turn.
    """
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
    """Mirror one container run's turn-record surface and archive it; records archived.

    Files already staged at the size the container reports are left alone — the common
    case on a live run, where every announce but the last concerns a file that is still
    the file it was.
    """
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
            flags["again"] = False  # a re-announce arrived mid-pull; go once more
    except Exception:  # noqa: BLE001 - a container whose records did not arrive is not a broken groom
        logger.debug("turn pull failed for %s", container, exc_info=True)
    finally:
        # The flag is released *after* the cleanup, not before it: a pull scheduled in
        # between would otherwise start re-creating the mirror in one thread while
        # another was still deleting it, and see files vanish under it mid-fetch.
        try:
            if flags["final"]:
                # The run is over, so the mirror has nothing left to save on the next
                # pull. Everything worth keeping is in the archive by now; this is only
                # the cache.
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
    """Ask for a pull without waiting for it.

    Fire-and-forget because the caller is the socket receive loop: a pull that blocked it
    would stall the ``progress`` and gate frames arriving on the same socket, which are
    the ones a human is watching.

    ``final`` marks the pull that follows a run reaching its terminal — after it, the
    staged mirror of that container is dropped.
    """
    container = conn.container_id
    flags = _IN_FLIGHT.get(container)
    if flags is not None:  # coalesce into the pass already running
        flags["again"] = True
        flags["final"] = flags["final"] or final
        return
    _IN_FLIGHT[container] = {"again": False, "final": final}
    task = asyncio.create_task(_pull_until_quiet(conn, run, run_id, workflow))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)


#: Strong references to the in-flight tasks. ``asyncio`` keeps only weak ones, so a task
#: nothing holds can be collected mid-await and the pull simply stops happening.
_TASKS: set[asyncio.Task] = set()
