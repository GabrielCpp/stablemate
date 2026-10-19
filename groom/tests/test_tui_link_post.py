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
    "/error": (400, {"error": "bad enabled"}),
    "/detail": (500, {"status_code": 500, "detail": "store is locked"}),
    "/bare": (502, {"unrelated": 1}),
    "/text": (500, "not json"),
}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        SEEN.append((self.path, self.headers.get("Content-Type") or "", raw))
        status, body = REPLIES[self.path]
        payload = body.encode() if isinstance(body, str) else json.dumps(body).encode()
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


def test_a_post_with_a_body_sends_json_with_its_content_type(base):
    assert asyncio.run(WsLink(base).post("/ok", {"enabled": True})) == {"ok": True}
    path, content_type, raw = SEEN[0]
    assert (path, content_type, json.loads(raw)) == ("/ok", "application/json", {"enabled": True})


def test_a_post_without_a_body_sends_no_content_type_and_no_bytes(base):
    assert asyncio.run(WsLink(base).post("/ok")) == {"ok": True}
    assert SEEN == [("/ok", "", b"")]


@pytest.mark.parametrize(
    ("path", "tail"),
    [("/error", "HTTP 400: bad enabled"), ("/detail", "HTTP 500: store is locked")],
)
def test_an_error_status_carries_the_error_or_detail_string(base, path, tail):
    with pytest.raises(LinkError) as caught:
        asyncio.run(WsLink(base).post(path, {"enabled": True}))
    assert str(caught.value) == f"POST {path}: {tail}"


@pytest.mark.parametrize(("path", "status"), [("/bare", 502), ("/text", 500)])
def test_an_error_status_without_a_string_reason_keeps_the_bare_message(base, path, status):
    with pytest.raises(LinkError) as caught:
        asyncio.run(WsLink(base).post(path))
    assert str(caught.value) == f"POST {path}: HTTP {status}"
