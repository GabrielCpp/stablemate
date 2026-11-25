from __future__ import annotations

from typing import Annotated

from litestar import post
from litestar.params import QueryParameter

from groom import (
    sidecar_hub,
)


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
