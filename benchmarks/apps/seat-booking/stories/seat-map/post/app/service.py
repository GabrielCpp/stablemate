"""The HTTP surface: the read routes over `http.server`, no third-party dependency.

The routing is a small hand-written table rather than a framework because the whole app has
to start from a stock Python image with nothing installed. What the layer *does* is
deliberately thin — parse, call one function in `booking.py`, serialise — so a defect
seeded in a status code and a defect seeded in a rule stay distinguishable.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from app import booking, page
from app.store import Store

#: The benchmark owns 18080-18099; seat-booking's number is recorded in
#: `benchmarks/suites/README.md` alongside every other spec's.
DEFAULT_PORT = 18083
DEFAULT_LEDGER = Path("/data/seats.json")


class Handler(BaseHTTPRequestHandler):
    """One request. `store` is set on the subclass built in `serve`."""

    store: Store
    protocol_version = "HTTP/1.1"
    server_version = "seat-booking"

    def do_GET(self) -> None:  # noqa: N802 - http.server's dispatch names
        if self.path in ("/", "/index.html"):
            self._html(200, page.render(booking.seat_map(self.store)))
        elif self.path == "/api/seats":
            self._json(200, {"seats": booking.seat_map(self.store)})
        elif self.path == "/healthz":
            self._json(200, {"status": "ok"})
        else:
            self._json(404, {"title": "Not Found"})

    # ── plumbing ──────────────────────────────────────────────────────────────────────

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        self._send(status, "application/json", json.dumps(payload).encode("utf-8"))

    def _html(self, status: int, body: str) -> None:
        self._send(status, "text/html; charset=utf-8", body.encode("utf-8"))

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - the base's name
        # One line per request on stdout, which is what `docker compose logs` shows and
        # what a failing QA scenario is read against.
        print(f"{self.address_string()} {format % args}", flush=True)


def serve(port: int = DEFAULT_PORT, ledger: Path = DEFAULT_LEDGER) -> None:
    handler = type("BoundHandler", (Handler,), {"store": Store(ledger)})
    server = ThreadingHTTPServer(("0.0.0.0", port), handler)  # noqa: S104 - a container
    print(f"seat-booking listening on :{port}, ledger {ledger}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    serve()
