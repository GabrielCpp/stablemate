"""A loopback stand-in for a booking service and the camera it leases, which the resource tests stand a book's resources on."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class BookingFake:
    """Serves `/health`, `/leases`, `/recordings` and `/play` on a free loopback port, and keeps what it was asked."""

    def __init__(self) -> None:
        self.leases: dict[str, str] = {}
        self.recordings: list[dict[str, Any]] = []
        self.requests: list[tuple[str, str, str]] = []
        self.refuse_once = False
        self.recording_delay = 0.3
        self.records_plays = True
        self._counter = 0
        self._lock = threading.Lock()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                return

            def _reply(self, status: int, body: object = None) -> None:
                payload = b"" if body is None else json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def _body(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                return json.loads(raw) if raw else {}

            def _seen(self) -> bool:
                with fake._lock:
                    fake.requests.append((self.command, self.path, self.headers.get("Authorization", "")))
                    if fake.refuse_once and self.path != "/health":
                        fake.refuse_once = False
                        self._reply(503, {"error": "busy"})
                        return False
                return True

            def do_GET(self) -> None:
                if not self._seen():
                    return
                if self.path == "/health":
                    self._reply(200, {"ok": True})
                elif self.path == "/leases":
                    self._reply(200, {"items": [{"id": key} for key in fake.leases]})
                elif self.path == "/recordings":
                    self._reply(200, {"items": list(fake.recordings)})
                else:
                    self._reply(404, {"error": "no such route"})

            def do_POST(self) -> None:
                if not self._seen():
                    return
                body = self._body()
                if self.path == "/leases":
                    with fake._lock:
                        fake._counter += 1
                        key = str(fake._counter)
                        fake.leases[key] = str(body.get("device", ""))
                    self._reply(201, {"id": key})
                elif self.path == "/play":
                    if fake.records_plays:
                        threading.Timer(
                            fake.recording_delay, lambda: fake.recordings.append({"video": body.get("video", "")})
                        ).start()
                    self._reply(202, {"accepted": True})
                else:
                    self._reply(404, {"error": "no such route"})

            def do_DELETE(self) -> None:
                if not self._seen():
                    return
                key = self.path.rpartition("/")[2]
                if self.path.startswith("/leases/") and key in fake.leases:
                    with fake._lock:
                        del fake.leases[key]
                    self._reply(204)
                else:
                    self._reply(404, {"error": "no such lease"})

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def start(self) -> "BookingFake":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def wait_for_leases(self, count: int, timeout: float = 5.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if len(self.leases) == count:
                return True
            time.sleep(0.05)
        return len(self.leases) == count


CAMERA_BOOKING_PAGE = """\
---
type: resource
title: Camera booking
---
# Camera booking

The booking service that leases the lab camera to one run at a time.

- reach: http
- base: $BOOKING_URL
- credential:
  - header: Authorization
  - scheme: Bearer
  - secret: CAMERA_BOOKING_TOKEN

## Probe

### answers

- kind: probe
- request: GET /health

## Observations

### leases

- kind: observe
- request: GET /leases
"""

CAMERA_PAGE = """\
---
type: resource
title: Camera
---
# Camera

- reach: http
- base: $CAMERA_URL

## Probe

### answers

- kind: probe
- request: GET /health

## Observations

### recordings

- kind: observe
- request: GET /recordings
"""

CAMERA_BOOKED_PAGE = """\
---
type: fixture
title: Camera booked
---
# Camera booked

- lifetime: scenario
- provides:
  - lease — the lease id the booking service issued
    - from: [take](#take)
    - read: id

## Steps

### take

- kind: borrow
- on: [Camera booking](../resources/camera-booking.md)
- request: POST /leases
- body: {"device": "camera-1"}

### give-back

- kind: release
- on: [Camera booking](../resources/camera-booking.md)
- request: DELETE /leases/$lease
"""

SERVER_PAGE = """\
---
type: server
title: Lab app
---
# Lab app

- entry-url: http://localhost:18101

## Endpoints

### play
- method: POST
- path: /play
- fixture: camera-booked
- arrange: no_body()
- status: 202 with the play accepted
- verify: json_path(path="$.accepted", equals=true)
- moves: none, because it only starts a video
- does: starts the calibration video on the camera
- observe: @camera.recordings
- verify: count(subject="items", equals=1, within=30)
"""


def write_booking_book(repo: Any) -> None:
    """Write the two resource pages, the borrowing fixture and the app endpoint that plays a video, under a service folder of *repo*."""
    base = repo / "docs/services/lab"
    for relative, text in (
        ("resources/camera-booking.md", CAMERA_BOOKING_PAGE),
        ("resources/camera.md", CAMERA_PAGE),
        ("fixtures/camera-booked.md", CAMERA_BOOKED_PAGE),
        ("server.md", SERVER_PAGE),
    ):
        target = base / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
