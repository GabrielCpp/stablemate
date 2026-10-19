from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from groom.tui.link import LinkError
from groom.tui.link_ws import WsLink

SEEN: list[tuple[str, str, bytes]] = []
REPLIES = {
    "/ok": (200, {"ok": True}),
    "/error": (404, {"ok": False, "error": "no such queue: q"}),
    "/bare": (502, {"unrelated": 1}),
    "/list": (200, [1]),
}


class Handler(BaseHTTPRequestHandler):
    def do_DELETE(self) -> None:
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        SEEN.append((self.command, self.path, raw))
        status, body = REPLIES[self.path]
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return None


@pytest.fixture
def base() -> Iterator[str]:
    SEEN.clear()
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join()
    server.server_close()


def test_a_delete_sends_the_method_with_no_body_and_returns_the_object(base):
    assert asyncio.run(WsLink(base).delete("/ok")) == {"ok": True}
    assert SEEN == [("DELETE", "/ok", b"")]


def test_a_delete_error_carries_the_error_text(base):
    with pytest.raises(LinkError) as caught:
        asyncio.run(WsLink(base).delete("/error"))
    assert str(caught.value) == "DELETE /error: HTTP 404: no such queue: q"


def test_a_delete_error_without_a_reason_keeps_the_bare_message(base):
    with pytest.raises(LinkError) as caught:
        asyncio.run(WsLink(base).delete("/bare"))
    assert str(caught.value) == "DELETE /bare: HTTP 502"


def test_a_delete_reply_that_is_not_an_object_is_refused(base):
    with pytest.raises(LinkError) as caught:
        asyncio.run(WsLink(base).delete("/list"))
    assert str(caught.value) == "DELETE /list: expected a JSON object"


def test_a_refused_connection_is_a_link_error():
    with pytest.raises(LinkError):
        asyncio.run(WsLink("http://127.0.0.1:1").delete("/ok"))
