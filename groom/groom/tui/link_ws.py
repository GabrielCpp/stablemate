from __future__ import annotations

import asyncio
import http.client
import json
from collections.abc import AsyncIterator
from urllib.parse import urlsplit

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, WebSocketException

from groom.tui.link import Frame, LinkError
from groom.ws_url import ws_url

MAX_FRAME_BYTES = 16 * 2**20
HTTP_TIMEOUT_S = 5.0
OPEN_TIMEOUT_S = 5.0


def _request(base: str, method: str, path: str) -> Frame:
    parts = urlsplit(base)
    factory = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
    target = parts.path.rstrip("/") + path
    connection = factory(parts.netloc, timeout=HTTP_TIMEOUT_S)
    try:
        connection.request(method, target, body=b"" if method == "POST" else None)
        body = json.loads(connection.getresponse().read())
    except (OSError, http.client.HTTPException, ValueError) as exc:
        raise LinkError(f"{method} {path}: {exc}") from exc
    finally:
        connection.close()
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
        return await asyncio.to_thread(_request, self._base, "GET", path)

    async def post(self, path: str) -> Frame:
        return await asyncio.to_thread(_request, self._base, "POST", path)

    async def close(self) -> None:
        socket, self._socket = self._socket, None
        if socket is not None:
            await socket.close()
