"""Host-side registry of the persistent sidecar sessions.

Each workflow container's ``groom-sidecar`` dials this ``groom`` process and
holds one WebSocket open (see :mod:`groom.sidecar`); ``app.dashboard_sidecar``
accepts it and registers a :class:`SidecarConnection` here. The connection is
the data plane for the Files/Diff panels: ``app`` issues ``getTree`` /
``getFile`` / ``getDiff`` RPCs down the same socket and the sidecar answers from
its local disk, so those reads no longer pay throwaway-container latency.

The registry is plain module-level state — single process, single event loop,
same constraint as :mod:`groom.state`. A connection is **non-authoritative**:
if it drops, callers fall back to the volume-read path and the reconcile scan
still owns removal, so a lost socket never strands a workflow.
"""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

# The default per-RPC timeout. A local-disk read on the sidecar is sub-ms; this
# bound only guards against a wedged or slow-to-answer sidecar so a panel fetch
# fails fast to the volume-read fallback instead of hanging the request.
RPC_TIMEOUT = 5.0


class _Sender(Protocol):
    async def send_json(self, data: Any) -> None: ...


class SidecarError(Exception):
    """An RPC could not be completed over the socket (timeout, closed
    connection, or an error result from the sidecar). Callers treat it as
    "socket unavailable" and fall back to the volume-read path."""


class SidecarConnection:
    """One live sidecar socket plus its outstanding RPCs.

    Correlation ids are a per-connection counter (not a random token): the
    single event loop hands out ids and resolves futures on the same loop, so a
    monotonic counter is collision-free and needs no locking.
    """

    def __init__(self, container_id: str, socket: _Sender) -> None:
        self.container_id = container_id
        self._socket = socket
        self._pending: dict[str, asyncio.Future] = {}
        self._counter = 0
        # Serialize sends: concurrent panel fetches (and a racing /reload) all
        # write to the one ASGI socket, which is not safe to send on from two
        # tasks at once.
        self._send_lock = asyncio.Lock()

    def _next_id(self) -> str:
        self._counter += 1
        return str(self._counter)

    async def _send(self, frame: dict[str, Any]) -> None:
        async with self._send_lock:
            await self._socket.send_json(frame)

    async def rpc(self, method: str, params: dict[str, Any], *, timeout: float = RPC_TIMEOUT) -> Any:
        """Send one ``getTree``/``getFile``/``getDiff`` request and await its
        result. Raises :class:`SidecarError` on timeout, a closed socket, or an
        error result — the caller then falls back to volume reads."""
        corr_id = self._next_id()
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[corr_id] = future
        try:
            await self._send({"type": "rpc", "id": corr_id, "method": method, "params": params})
        except Exception as exc:  # noqa: BLE001 - any send failure means the socket is unusable
            self._pending.pop(corr_id, None)
            raise SidecarError(f"send failed: {exc}") from exc
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise SidecarError(f"{method} timed out after {timeout}s") from exc
        finally:
            self._pending.pop(corr_id, None)

    def resolve(self, corr_id: str, *, ok: bool, data: Any = None, error: str = "") -> None:
        """Fold an ``rpc_result`` frame from the sidecar back into the waiting
        RPC. A late/duplicate/unknown id is ignored (the future is already gone
        after a timeout), so a slow sidecar answering after the deadline can't
        raise."""
        future = self._pending.get(corr_id)
        if future is None or future.done():
            return
        if ok:
            future.set_result(data)
        else:
            future.set_exception(SidecarError(error or "sidecar reported an error"))

    def fail_all(self, message: str) -> None:
        """Reject every outstanding RPC — called when the socket closes so
        in-flight panel fetches fail fast to the fallback instead of waiting out
        their timeouts."""
        for future in self._pending.values():
            if not future.done():
                future.set_exception(SidecarError(message))
        self._pending.clear()

    async def send_reload(self) -> None:
        """Ask this sidecar to reload its code (exit 3; the entrypoint recopies
        the edited source and relaunches). Best-effort — a dead socket just
        means there is nothing to reload."""
        await self._send({"type": "reload"})


CONNECTIONS: dict[str, SidecarConnection] = {}


def register(conn: SidecarConnection) -> None:
    """Register a sidecar connection, displacing any prior one for the same
    container (a reconnect supersedes the stale socket) and failing the old
    one's pending RPCs so they don't linger."""
    existing = CONNECTIONS.get(conn.container_id)
    if existing is not None and existing is not conn:
        existing.fail_all("superseded by a new sidecar connection")
    CONNECTIONS[conn.container_id] = conn


def unregister(conn: SidecarConnection) -> None:
    """Drop a connection on socket close, but only if it is still the current
    one — a late close from a superseded socket must not evict the live
    reconnect that already replaced it."""
    if CONNECTIONS.get(conn.container_id) is conn:
        CONNECTIONS.pop(conn.container_id, None)
    conn.fail_all("sidecar connection closed")


def get(container_id: str) -> SidecarConnection | None:
    return CONNECTIONS.get(container_id)


def connected_ids() -> list[str]:
    return list(CONNECTIONS)
