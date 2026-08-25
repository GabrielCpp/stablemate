"""The acceptance gate's contract, proved without Go or an emulator.

`_linkshort.run_checks` is pure over HTTP plus a restart callable, which is what makes it
testable at all: a correct in-memory server must score 12/12, and a server that skips
validation and forgets its ledger on restart must fail exactly those checks. The real
`probe` wrapper — build, emulator, ports — is exercised by running the task; what lives
here is the ruler, because a gate that grades the wrong claims is worse than no gate.
"""

from __future__ import annotations

import contextlib
import importlib
import json
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

DATA = Path(__file__).parents[1]


@contextlib.contextmanager
def _tasks_dir_on_path() -> Iterator[None]:
    saved = sys.path[:]
    sys.path.insert(0, str(DATA / "tasks"))
    try:
        yield
    finally:
        sys.path[:] = saved


with _tasks_dir_on_path():
    linkshort = importlib.import_module("_linkshort")


class _Faithful(BaseHTTPRequestHandler):
    """A minimal correct product: validates, mints distinct keys, survives restarts."""

    store: dict[str, str] = {}
    minted = 0
    validates = True
    durable = True

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib's spelling
        return

    def _send(self, status: int, payload: dict[str, str]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's spelling
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            payload = {}
        url = payload.get("url")
        valid = isinstance(url, str) and url.startswith(("http://", "https://"))
        if not valid and (self.validates or not isinstance(url, str) or not url):
            self._send(400, {"title": "Invalid destination"})
            return
        cls = type(self)
        cls.minted += 1
        key = f"k{cls.minted:06d}"
        cls.store[key] = str(url)
        base = f"http://{self.headers.get('Host')}"
        self._send(201, {"key": key, "short_url": f"{base}/{key}"})

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's spelling
        key = self.path.lstrip("/")
        destination = self.store.get(key)
        if destination is None:
            self._send(404, {"title": "Not Found"})
            return
        self.send_response(302)
        self.send_header("Location", destination)
        self.end_headers()


class _Sloppy(_Faithful):
    """Accepts anything with a `url` string and loses its ledger on restart."""

    store: dict[str, str] = {}
    minted = 0
    validates = False
    durable = False


@contextlib.contextmanager
def _serving(handler: type[_Faithful]) -> Iterator[str]:
    handler.store = {}
    handler.minted = 0
    server = ThreadingHTTPServer(("localhost", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://localhost:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _restart(handler: type[_Faithful]) -> None:
    if not handler.durable:
        handler.store = {}


def test_a_faithful_product_scores_full_marks() -> None:
    with _serving(_Faithful) as base:
        checks = linkshort.run_checks(base, lambda: _restart(_Faithful))
    assert len(checks) == linkshort.TOTAL
    assert [check["name"] for check in checks if not check["ok"]] == []


def test_the_gate_names_what_a_sloppy_product_skips() -> None:
    with _serving(_Sloppy) as base:
        checks = linkshort.run_checks(base, lambda: _restart(_Sloppy))
    assert len(checks) == linkshort.TOTAL
    not_ok = {check["name"] for check in checks if not check["ok"]}
    assert not_ok == {
        "relative url is a 400",
        "javascript url is a 400",
        "key survives a server restart",
    }


def test_nothing_listening_is_twelve_answered_failures() -> None:
    """A dead server scores 0 of 12 with every row present, not an exception."""
    checks = linkshort.run_checks("http://localhost:9", lambda: None)
    assert len(checks) == linkshort.TOTAL
    assert all(not check["ok"] for check in checks)
