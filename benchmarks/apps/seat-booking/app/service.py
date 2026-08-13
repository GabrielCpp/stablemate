"""The HTTP surface: five routes over `http.server`, no third-party dependency.

The routing is a small hand-written table rather than a framework because the whole app has
to start from a stock Python image with nothing installed. What the layer *does* is
deliberately thin — parse, call one transition in `booking.py`, serialise — so a defect
seeded in a status code and a defect seeded in a rule stay distinguishable.
"""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from app import booking, page
from app.store import Store

#: The benchmark owns 18080-18099; seat-booking's number is recorded in
#: `benchmarks/suites/README.md` alongside every other spec's.
DEFAULT_PORT = 18083
DEFAULT_LEDGER = Path("/data/seats.json")

SEAT_HOLD = re.compile(r"^/api/seats/([A-Za-z0-9]+)/hold$")
SEAT_BOOKING = re.compile(r"^/api/seats/([A-Za-z0-9]+)/booking$")


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

    def do_POST(self) -> None:  # noqa: N802
        hold = SEAT_HOLD.match(self.path)
        book = SEAT_BOOKING.match(self.path)
        try:
            if hold:
                self._json(201, {"hold": booking.hold(self.store, hold.group(1))})
            elif book:
                body = self._body()
                version = body.get("version")
                if not isinstance(version, int):
                    self._json(400, {"title": "Version Required"})
                    return
                name = str(body.get("name") or "").strip()
                if not name:
                    self._json(400, {"title": "Name Required"})
                    return
                created = booking.confirm(
                    self.store, book.group(1), version=version, name=name
                )
                self._json(201, {"booking": created})
            else:
                self._json(404, {"title": "Not Found"})
        except booking.Conflict as refused:
            self._json(refused.refusal.status, {"title": refused.refusal.title})

    def do_DELETE(self) -> None:  # noqa: N802
        hold = SEAT_HOLD.match(self.path)
        if not hold:
            self._json(404, {"title": "Not Found"})
            return
        try:
            booking.release(self.store, hold.group(1))
        except booking.Conflict as refused:
            self._json(refused.refusal.status, {"title": refused.refusal.title})
            return
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ── plumbing ──────────────────────────────────────────────────────────────────────

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            loaded = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, dict) else {}

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
