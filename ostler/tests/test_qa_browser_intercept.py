"""A request rule alters the server's answer on its way to the browser, whoever sent the request."""

from __future__ import annotations

import json
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
fetch('/api/figures').then(r => r.json()).then(d => {
  document.getElementById('out').textContent = String(d.total);
});
</script>"""

_WORKER_PAGE = b"""<!doctype html><title>t</title><div id="out"></div><script>
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
  const total = (await (await fetch('/api/figures')).json()).total;
  const clients = await self.clients.matchAll();
  clients.forEach(c => c.postMessage(String(total)));
});"""

_FIGURES = json.dumps({"total": 1300}).encode()


class _App(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        kind, body = {
            "/": ("text/html", _PAGE),
            "/worker": ("text/html", _WORKER_PAGE),
            "/sw.js": ("text/javascript", _WORKER),
            "/api/figures": ("application/json", _FIGURES),
        }.get(self.path, ("text/plain", b""))
        self.send_response(200 if body else 404)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
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


def _recording(tmp_path: Path) -> Any:
    return browser_module.Browser(
        SimpleNamespace(browser=None, permissions=None, recording={"required": False}, viewport=None),
        qa_dir=tmp_path, scenario_id="intercept", clock=lambda: 0, emit=lambda *_: None,
    )


def test_a_rewrite_changes_the_figure_the_page_writes_into_the_dom(origin: str, tmp_path: Path) -> None:
    recording = _recording(tmp_path)
    page = recording.open()
    try:
        recording.intercept("rewrite", event="GET /api/figures", find="1300", replace="4200")
        page.goto(f"{origin}/")
        page.wait_for_function("document.getElementById('out').textContent !== ''")
        recording.quiet()
        assert page.inner_text("#out") == "4200"
        sent = [entry for entry in recording.requests(initiator=None) if entry["url"].endswith("/api/figures")]
        assert [entry["intercepted"] for entry in sent] == [{"effect": "rewrite", "replacements": 1}]
        assert recording.unclean() == []
    finally:
        recording.close(failed=False)
    written = json.loads((tmp_path / "traces" / "intercept-diagnostics.json").read_text(encoding="utf-8"))
    assert written["schema"] == "browser-diagnostics/3"
    assert written["intercepts"] == [{
        "effect": "rewrite", "event": "GET /api/figures", "find": "1300", "replace": "4200",
        "matched": 1, "rewritten": 1,
    }]


def test_a_rewrite_applies_to_a_request_the_service_worker_sends(origin: str, tmp_path: Path) -> None:
    recording = _recording(tmp_path)
    page = recording.open()
    try:
        recording.intercept("rewrite", event="GET /api/figures", find="1300", replace="4200")
        page.goto(f"{origin}/worker")
        page.wait_for_function("document.getElementById('out').textContent !== ''")
        recording.quiet()
        assert page.inner_text("#out") == "4200"
        sent = [entry for entry in recording.requests(initiator=None) if entry["url"].endswith("/api/figures")]
        assert [(entry["initiator"], entry["intercepted"]["replacements"]) for entry in sent] == [("worker", 1)]
    finally:
        recording.close(failed=False)


def test_a_request_with_another_method_reaches_the_server_untouched(origin: str, tmp_path: Path) -> None:
    recording = _recording(tmp_path)
    page = recording.open()
    try:
        recording.intercept("rewrite", event="POST /api/figures", find="1300", replace="4200")
        page.goto(f"{origin}/")
        page.wait_for_function("document.getElementById('out').textContent !== ''")
        recording.quiet()
        assert page.inner_text("#out") == "1300"
        assert recording.unclean() == [
            "intercept rewrite POST /api/figures matched 0 exchanges and rewrote 0: no exchange reached the rule"
        ]
    finally:
        recording.close(failed=False)
