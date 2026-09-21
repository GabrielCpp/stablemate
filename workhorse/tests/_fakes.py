"""Test doubles for the ports the runner is handed, plus the one shared assertion helper."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from workhorse import otel
from workhorse.runner.backends import AgentBackend


def present[T](value: T | None) -> T:
    """``value`` with its ``None`` ruled out — for a lookup the test arranged to hit."""
    assert value is not None
    return value


class FakeBackend(AgentBackend):
    """An ``AgentBackend`` whose two operations are plain functions the test supplies."""

    name = "fake"
    supports_compaction = True

    def __init__(self, turn: Any = None, compact: Any = None) -> None:
        self._turn = turn
        self._compact = compact

    def harness_env(self) -> dict[str, str]:
        return {}

    def run_turn(
        self,
        prompt: str,
        node_id: str,
        session_id_path: Path | None,
        model: str | None = None,
        **kwargs: Any,
    ) -> str:
        if self._turn is None:
            raise AssertionError("FakeBackend.run_turn called but no turn was supplied")
        return self._turn(prompt, node_id, session_id_path, model, **kwargs)

    def compact(
        self,
        session_id_path: Path | None,
        node_id: str,
        model: str | None = None,
        **kwargs: Any,
    ) -> bool:
        if self._compact is None:
            raise AssertionError("FakeBackend.compact called but no compact was supplied")
        return self._compact(session_id_path, node_id, model, **kwargs)


class FakeClock:
    """A ``Clock`` that records what it was asked to wait and never waits."""

    def __init__(self, now: datetime | None = None) -> None:
        self._now = now or datetime(2026, 1, 1, 12, 0, 0)
        self._elapsed = 0.0
        self.slept: list[float] = []

    def now(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        """Elapsed seconds since this clock's own zero, moved only by ``sleep``."""
        return self._elapsed

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self._elapsed += seconds
        self._now += timedelta(seconds=seconds)


class RecordingTelemetry(otel._NullTelemetry):
    """Telemetry that remembers what was published, for tests that assert on it."""

    def __init__(self) -> None:
        self.beats: list[tuple[str, float, float]] = []
        self.labels: list[dict[str, str]] = []
        self.states: list[tuple[str, str, int, str | None]] = []
        self.cuts: list[tuple[str, str]] = []
        self.waits: list[tuple[str, int, str, str]] = []
        self.gates: list[tuple[str, str]] = []
        self.events: list[tuple[str, bool, dict[str, Any]]] = []
        self.turns_opened: list[str] = []
        self.turns_closed: list[str | None] = []
        self.ended: list[str] = []
        self.run_attributes: list[tuple[str, str]] = []
        self._wait_token = 0

    def enabled(self) -> bool:
        return True

    def turn_heartbeat(self, node_id: str, idle_s: float, elapsed_s: float) -> None:
        self.beats.append((node_id, idle_s, elapsed_s))

    def set_labels(self, labels: dict[str, str]) -> None:
        self.labels.append(dict(labels))

    def run_attribute(self, name: str, value: str) -> None:
        self.run_attributes.append((name, value))

    def turn_event(self, name: str, error: bool, attrs: dict[str, Any]) -> None:
        self.events.append((name, error, dict(attrs)))

    def turn_start(
        self,
        node_id: str,
        model: str | None,
        effort: str | None,
        timeout: float,
        backend: str | None = None,
        cwd: str | None = None,
        add_dirs: tuple[str, ...] = (),
    ) -> None:
        self.turns_opened.append(node_id)

    def turn_end(
        self, error: str | None = None, error_class: str = "", error_kind: str = ""
    ) -> None:
        self.turns_closed.append(error)

    def state_start(self, state: str, seq: int) -> None:
        self.states.append(("start", state, seq, None))

    def state_end(
        self, state: str, seq: int, next_state: str | None = None, cut: str = ""
    ) -> None:
        self.states.append(("end", state, seq, next_state))
        if cut:
            self.cuts.append((state, cut))

    def end_run(
        self,
        status: str,
        error: str | None = None,
        error_class: str = "",
        error_kind: str = "",
    ) -> None:
        self.ended.append(status)

    def wait_start(
        self,
        kind: str,
        node_id: str,
        gate_path: str = "",
        gate_question: str = "",
    ) -> int:
        self._wait_token += 1
        self.waits.append(("start", self._wait_token, kind, node_id))
        self.gates.append((gate_path, gate_question))
        return self._wait_token

    def wait_end(self, token: int, outcome: str = "completed") -> None:
        self.waits.append(("end", token, outcome, ""))


@contextmanager
def fake_groom(rows: list[dict[str, str]]) -> Iterator[tuple[str, list[str]]]:
    """A stand-in for ``groom serve`` answering ``/api/live`` with the given rows."""
    asked: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - http.server's spelling
            asked.append(self.path)
            body = json.dumps(rows).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", asked
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
