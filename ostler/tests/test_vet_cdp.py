"""Live-scan smoke test: the one vet test allowed to be slow/skippable when `playwright`
(or its browser binary) isn't installed. Every other vet test stays fast and dependency-free.
"""
from __future__ import annotations

import functools
import http.server
import threading
from pathlib import Path

import pytest

pytest.importorskip("playwright")

from ostler.vet.cdp import connect_and_scan  # noqa: E402 — after importorskip

_PORT = 9377

_HTML = """<!doctype html>
<html><body>
<nav id="nav" style="width:100px;height:40px;">Nav</nav>
<aside id="aside" style="width:80px;height:200px;">Aside</aside>
<form id="form" style="width:300px;height:150px;"><input></form>
</body></html>
"""


def _serve(root: Path) -> http.server.ThreadingHTTPServer:
    (root / "index.html").write_text(_HTML, encoding="utf-8")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_connect_and_scan_finds_landmark_roles(tmp_path: Path):
    from playwright.sync_api import sync_playwright

    server = _serve(tmp_path)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=[f"--remote-debugging-port={_PORT}"])
            try:
                page = browser.new_page()
                page.goto(f"http://127.0.0.1:{server.server_address[1]}/index.html")
                elements = connect_and_scan(f"http://127.0.0.1:{_PORT}")
            finally:
                browser.close()
    finally:
        server.shutdown()

    roles = {el.role for el in elements}
    assert "navigation" in roles
    assert "complementary" in roles
    assert "form" in roles
