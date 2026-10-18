from __future__ import annotations

import asyncio
import http.client
import json
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlsplit

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, WebSocketException

from groom.tui.link import Frame, LinkError
from groom.ws_url import ws_url

MAX_FRAME_BYTES = 16 * 2**20
HTTP_TIMEOUT_S = 5.0
OPEN_TIMEOUT_S = 5.0


def _reason(raw: bytes) -> str:
    try:
        body = json.loads(raw)
    except ValueError:
        return ""
    if not isinstance(body, dict):
        return ""
    for name in ("error", "detail"):
        if isinstance(body.get(name), str):
            return body[name]
    return ""


def _request(base: str, method: str, path: str, body: Frame | None = None) -> Any:
    parts = urlsplit(base)
    factory = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
    target = parts.path.rstrip("/") + path
    connection = factory(parts.netloc, timeout=HTTP_TIMEOUT_S)
    try:
        payload = b"" if method == "POST" else None
        headers = {}
        if body is not None:
            payload = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        connection.request(method, target, body=payload, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        if response.status >= 400:
            reason = _reason(raw)
            raise LinkError(f"{method} {path}: HTTP {response.status}" + (f": {reason}" if reason else ""))
        decoded = json.loads(raw)
    except (OSError, http.client.HTTPException, ValueError) as exc:
        raise LinkError(f"{method} {path}: {exc}") from exc
    finally:
        connection.close()
    return decoded


def _object(body: Any, method: str, path: str) -> Frame:
    if not isinstance(body, dict):
        raise LinkError(f"{method} {path}: expected a JSON object")
    return body


class WsLink:
    def __init__(self, url: str) -> None:
        self._base = url
        self._ws_url = ws_url(url, "/ws")
        self._socket: ClientConnection | None = None

    async def open(self) -> None:
        await self.close()
        try:
            self._socket = await connect(
                self._ws_url, open_timeout=OPEN_TIMEOUT_S, max_size=MAX_FRAME_BYTES
            )
        except (OSError, TimeoutError, WebSocketException) as exc:
            raise LinkError(str(exc)) from exc

    async def frames(self) -> AsyncIterator[Frame]:
        socket = self._socket
        if socket is None:
            return
        try:
            async for raw in socket:
                try:
                    frame = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(frame, dict):
                    yield frame
        except ConnectionClosed:
            return

    async def send(self, command: Frame) -> bool:
        socket = self._socket
        if socket is None:
            return False
        try:
            await socket.send(json.dumps(command))
        except ConnectionClosed:
            return False
        return True

    async def get(self, path: str) -> Frame:
        return _object(await asyncio.to_thread(_request, self._base, "GET", path), "GET", path)

    async def get_list(self, path: str) -> list[Frame]:
        body = await asyncio.to_thread(_request, self._base, "GET", path)
        if not isinstance(body, list):
            raise LinkError(f"GET {path}: expected a JSON list")
        return body

    async def post(self, path: str, body: Frame | None = None) -> Frame:
        reply = await asyncio.to_thread(_request, self._base, "POST", path, body)
        return _object(reply, "POST", path)

    async def close(self) -> None:
        socket, self._socket = self._socket, None
        if socket is not None:
            await socket.close()
