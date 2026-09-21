"""Host-side registry of the persistent sidecar sessions."""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

RPC_TIMEOUT = 5.0


class _Sender(Protocol):
    async def send_json(self, data: Any) -> None: ...


class SidecarError(Exception):
    """An RPC could not be completed over the socket (timeout, closed connection, or an error result from the sidecar)."""


class SidecarConnection:
    """One live sidecar socket plus its outstanding RPCs."""

    def __init__(self, container_id: str, socket: _Sender) -> None:
        self.container_id = container_id
        self._socket = socket
        self._pending: dict[str, asyncio.Future] = {}
        self._counter = 0
        self._send_lock = asyncio.Lock()

    def _next_id(self) -> str:
        self._counter += 1
        return str(self._counter)

    async def _send(self, frame: dict[str, Any]) -> None:
        async with self._send_lock:
            await self._socket.send_json(frame)

    async def rpc(self, method: str, params: dict[str, Any], *, timeout: float = RPC_TIMEOUT) -> Any:
        """Send one ``getTree``/``getFile``/``getDiff`` request and await its result."""
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
        """Fold an ``rpc_result`` frame from the sidecar back into the waiting RPC."""
        future = self._pending.get(corr_id)
        if future is None or future.done():
            return
        if ok:
            future.set_result(data)
        else:
            future.set_exception(SidecarError(error or "sidecar reported an error"))

    def fail_all(self, message: str) -> None:
        """Reject every outstanding RPC — called when the socket closes so in-flight panel fetches fail fast to the fallback instead of waiting out their timeouts."""
        for future in self._pending.values():
            if not future.done():
                future.set_exception(SidecarError(message))
        self._pending.clear()

    async def send_reload(self) -> None:
        """Ask this sidecar to reload its code (exit 3; the entrypoint recopies the edited source and relaunches)."""
        await self._send({"type": "reload"})


CONNECTIONS: dict[str, SidecarConnection] = {}


def register(conn: SidecarConnection) -> None:
    """Register a sidecar connection, displacing any prior one for the same container (a reconnect supersedes the stale socket) and failing the old one's pending RPCs so they don't linger."""
    existing = CONNECTIONS.get(conn.container_id)
    if existing is not None and existing is not conn:
        existing.fail_all("superseded by a new sidecar connection")
    CONNECTIONS[conn.container_id] = conn


def unregister(conn: SidecarConnection) -> None:
    """Drop a connection on socket close, but only if it is still the current one — a late close from a superseded socket must not evict the live reconnect that already replaced it."""
    if CONNECTIONS.get(conn.container_id) is conn:
        CONNECTIONS.pop(conn.container_id, None)
    conn.fail_all("sidecar connection closed")


def get(container_id: str) -> SidecarConnection | None:
    return CONNECTIONS.get(container_id)


def connected_ids() -> list[str]:
    return list(CONNECTIONS)


async def _gate_rpc(container_id: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
    conn = get(container_id)
    if conn is None:
        raise SidecarError(f"no sidecar connected for {container_id}")
    reply = await conn.rpc(method, params)
    if not isinstance(reply, dict):
        raise SidecarError(f"{method} returned a non-dict reply: {reply!r}")
    return reply


async def ask_questions(container_id: str, run: str = "") -> dict[str, Any]:
    """The pending operator questions of one containerised run, asked over its own control socket via the sidecar's ``getQuestions`` relay."""
    return await _gate_rpc(container_id, "getQuestions", {"run": run})


async def answer_gate(container_id: str, run: str, path: str, body: str) -> dict[str, Any]:
    """Deliver one operator answer to a containerised run over its control socket, via the sidecar's ``answerGate`` relay."""
    params = {"run": run, "path": path, "body": body}
    return await _gate_rpc(container_id, "answerGate", params)
