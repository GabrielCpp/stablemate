from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from groom.tui.link import LinkError
from groom.tui.link_ws import WsLink

REPLIES = {
    "/object": (200, {"ok": True}),
    "/list": (200, [{"a": 1}]),
    "/broken": (500, {"error": "boom"}),
    "/missing": (404, [{"error": "nope"}]),
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        status, body = REPLIES[self.path]
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format: str, *args: object) -> None:
        return None


@pytest.fixture
def base() -> Iterator[str]:
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join()
    server.server_close()


def test_get_returns_an_object_and_get_list_returns_a_list(base):
    link = WsLink(base)
    assert asyncio.run(link.get("/object")) == {"ok": True}
    assert asyncio.run(link.get_list("/list")) == [{"a": 1}]


def test_an_error_status_raises_even_when_the_body_is_json(base):
    link = WsLink(base)
    with pytest.raises(LinkError, match="HTTP 500"):
        asyncio.run(link.get("/broken"))
    with pytest.raises(LinkError, match="HTTP 404"):
        asyncio.run(link.get_list("/missing"))


def test_get_raises_on_a_list_body(base):
    with pytest.raises(LinkError, match="JSON object"):
        asyncio.run(WsLink(base).get("/list"))


def test_get_list_raises_on_an_object_body(base):
    with pytest.raises(LinkError, match="JSON list"):
        asyncio.run(WsLink(base).get_list("/object"))
