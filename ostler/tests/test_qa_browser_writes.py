"""A step that opens a new address waits for the save the step before it started, as a user waits for it to land."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ostler.qa.harness_host import load_harness_module

browser_module = load_harness_module("ostler_qa_browser")
sync_api = pytest.importorskip("playwright.sync_api")

_PAGE = b"""<!doctype html><title>t</title>
<button onclick="fetch('/items/1', {method: 'DELETE'})">Remove</button>"""


class _SlowDelete(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(_PAGE)

    def do_DELETE(self) -> None:
        time.sleep(0.8)
        self.send_response(204)
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        return


@pytest.fixture
def origin() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _SlowDelete)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


def test_leaving_the_page_waits_for_a_removal_in_flight(origin: str, tmp_path: Path) -> None:
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page()
            listening = browser_module.Browser(
                SimpleNamespace(recording=None, viewport=None),
                qa_dir=tmp_path, scenario_id="remove", clock=lambda: 0, emit=lambda *_: None,
            )
            listening._listen(page)
            listening.page = page
            page.goto(f"{origin}/")
            page.get_by_role("button", name="Remove").click()
            listening.writes_done()
            page.goto(f"{origin}/")
            removals = [entry for entry in listening.responses() if entry.get("method") == "DELETE"]
            assert [entry["status"] for entry in removals] == [204]
        finally:
            browser.close()
