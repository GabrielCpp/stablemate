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
from app.store import Store, empty_ledger

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

    def do_DELETE(self) -> None:  # noqa: N802
        if self.path != "/api/showing":
            self._json(404, {"title": "Not Found"})
            return
        self._reset_showing()

    def _reset_showing(self) -> None:
        """Empty the ledger: every seat free again, at version 0.

        A fixed twelve-seat showing is a finite resource, and QA drives it repeatedly — a
        rehearsal, then the scored execution, then a re-run after a repair. Without a way to
        put the showing back, the third pass fails for having no free seat rather than for
        anything the story claims, which reads as a defect in whichever scenario happened to
        run last. So the reset is part of the product and part of the book, not a lever the
        harness reaches around it for.
        """
        self.store.write(empty_ledger())
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

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
