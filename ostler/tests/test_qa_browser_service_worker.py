"""A request a service worker sends itself is recorded, and says the worker sent it."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ostler.qa.harness_host import load_harness_module

browser_module = load_harness_module("ostler_qa_browser")
pytest.importorskip("playwright.sync_api")

_PAGE = b"""<!doctype html><title>t</title><div id="out"></div><script>
(async () => {
  await navigator.serviceWorker.register('/sw.js', {scope: '/'});
  await navigator.serviceWorker.ready;
  if (!navigator.serviceWorker.controller) {
    await new Promise(r => navigator.serviceWorker.addEventListener('controllerchange', r, {once: true}));
  }
  navigator.serviceWorker.addEventListener('message', e => { document.getElementById('out').textContent = e.data; });
  navigator.serviceWorker.controller.postMessage('go');
})();
</script>"""

_WORKER = b"""self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('message', async e => {
  const text = await (await fetch('/api/from-sw')).text();
  const clients = await self.clients.matchAll();
  clients.forEach(c => c.postMessage(text));
});"""


class _App(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        kind, body = {
            "/": ("text/html", _PAGE),
            "/sw.js": ("text/javascript", _WORKER),
            "/api/from-sw": ("text/plain", b"from the worker"),
        }.get(self.path, ("text/plain", b""))
        self.send_response(200 if body else 404)
        self.send_header("Content-Type", kind)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


@pytest.fixture
def origin() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _App)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


def test_a_request_the_service_worker_sends_is_recorded_as_the_workers(origin: str, tmp_path: Path) -> None:
    recording = browser_module.Browser(
        SimpleNamespace(browser=None, permissions=None, recording={"required": False}, viewport=None),
        qa_dir=tmp_path, scenario_id="worker", clock=lambda: 0, emit=lambda *_: None,
    )
    page = recording.open()
    try:
        page.goto(f"{origin}/")
        page.wait_for_function("document.getElementById('out').textContent !== ''")
        recording.quiet()
        sent = [entry for entry in recording.requests(initiator=None) if entry["url"].endswith("/api/from-sw")]
        assert [entry["initiator"] for entry in sent] == ["worker"]
        assert recording.requests(url_contains="/api/from-sw") == []
        assert recording.response_for("/api/from-sw", initiator="worker").text == "from the worker"
    finally:
        recording.close(failed=False)
