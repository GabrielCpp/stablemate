"""Tailing a run's transcript files into its open pane's history: from disk for a native run, over the sidecar socket for a container's."""
from __future__ import annotations

import base64
import logging
from typing import Any

from groom import localfs, sidecar_turns, state
from groom.live_history import LiveHistory

logger = logging.getLogger(__name__)

TAILED_TURNS = 2

MAX_TAIL_BYTES = 4 * 1024 * 1024


def poll(history: LiveHistory, run_dir: str) -> None:
    """Feed the newest turns' new complete lines to ``history``; a seeding call is a poll from offset zero."""
    files = localfs.transcript_files(run_dir)
    for slug in sorted(files)[-TAILED_TURNS:]:
        data = localfs.read_range(files[slug], history.offsets.get(slug, 0))
        if data:
            history.feed_transcript(slug, data)


async def _read_new(conn: Any, history: LiveHistory, run: str, slug: str, rel: str) -> None:
    """Feed one remote file's bytes past the history's offset, a chunk at a time, taking the history lock only to feed."""
    offset = history.offsets.get(slug, 0)
    read = 0
    while read < MAX_TAIL_BYTES:
        reply = await conn.rpc(
            "readTurnFile",
            {"run": run, "path": rel, "offset": offset},
            timeout=sidecar_turns.RPC_TIMEOUT,
        )
        chunk = base64.b64decode(str((reply or {}).get("data", "")))
        if not chunk:
            return
        async with state.HISTORY_LOCK:
            history.feed_transcript(slug, chunk)
        offset += len(chunk)
        read += len(chunk)
        if (reply or {}).get("eof"):
            return


async def tail(conn: Any, history: LiveHistory, run: str) -> None:
    """Feed the newest turns' new complete lines from a container's run dir to ``history``; a failed read leaves the history as it was."""
    try:
        listing = await conn.rpc("listTurns", {"run": run}, timeout=sidecar_turns.RPC_TIMEOUT)
        if not isinstance(listing, dict):
            return
        remote_run = str(listing.get("run", "") or run)
        sizes = {str((entry or {}).get("path", "")): int((entry or {}).get("size", 0)) for entry in listing.get("files") or []}
        picked = localfs.pick_transcripts(sizes)
        for slug in sorted(picked)[-TAILED_TURNS:]:
            if sizes[picked[slug]] > history.offsets.get(slug, 0):
                await _read_new(conn, history, remote_run, slug, picked[slug])
    except Exception:  # noqa: BLE001 - a container whose transcript did not arrive is not a broken groom
        logger.debug("transcript tail failed for %s", conn.container_id, exc_info=True)
