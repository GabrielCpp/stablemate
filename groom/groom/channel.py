"""``groom channel``: a stdio MCP server that pushes the /feed of the runs a Claude Code session watches into that session."""
from __future__ import annotations

import json
import sys
import threading
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Protocol

from websockets.exceptions import WebSocketException
from websockets.sync.client import connect

from groom.attention import DigestFrame, EventFrame
from groom.wait import endpoint, event_line, frames

PROTOCOL_VERSION = "2025-06-18"
DEFAULT_EVERY_MIN = 30.0
MAX_RETRY_S = 30.0

INSTRUCTIONS = (
    "groom pushes workhorse run updates into this session. Call the watch tool with a run_id to follow a run. "
    'Updates arrive as <channel source="groom" run_id="..." kind="...">. '
    "kind=event is an attention event the moment it fires: blocked (an operator gate waits for an answer), "
    "ended, stuck, stalled, gave-up, churn, watchdog, died or waiting. The event attribute names it. "
    "kind=digest is the periodic summary of the run, sent even when nothing happened. "
    "kind=connection reports that groom became unreachable or came back. After a loss the watch replays what it "
    "missed, so nothing is dropped. These are one-way: act on them, no reply goes back through the channel."
)

WATCH_TOOL: dict[str, Any] = {
    "name": "watch",
    "description": (
        "Push a workhorse run's groom feed into this session: each attention event as it fires and a digest "
        "on an interval. Call again with stop=true to end the watch."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "run_id": {"type": "string", "description": "Exact run_id to follow."},
            "every_minutes": {
                "type": "number",
                "description": f"Digest interval in minutes, at least 1 (default {DEFAULT_EVERY_MIN:g}).",
            },
            "stop": {"type": "boolean", "description": "End the watch on this run instead of starting one."},
        },
        "required": ["run_id"],
    },
}


class FeedSocket(Protocol):
    def recv(self) -> str | bytes: ...

    def close(self) -> None: ...


Connect = Callable[[str], AbstractContextManager[FeedSocket]]
Send = Callable[[dict[str, Any]], None]


def _connect(address: str) -> AbstractContextManager[FeedSocket]:
    return connect(address, open_timeout=5, close_timeout=1, ping_interval=20, ping_timeout=20)


def _server_version() -> str:
    try:
        return version("stablemate-groom")
    except PackageNotFoundError:
        return "0"


class Watch:
    """One run's feed, kept connected until stopped; a reconnect asks for every frame after the last one seen."""

    def __init__(
        self, *, url: str, run: str, every_s: float, notify: Callable[[str, dict[str, str]], None],
        connect: Connect, retry_s: float,
    ) -> None:
        self.run = run
        self._url = url
        self._every_s = every_s
        self._notify = notify
        self._connect = connect
        self._retry_s = retry_s
        self._since: float | None = None
        self._stopped = threading.Event()
        self._socket: FeedSocket | None = None
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._follow, name=f"groom-watch-{run}", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stopped.set()
        with self._lock:
            socket = self._socket
        if socket is not None:
            socket.close()
        self._thread.join(timeout=5)

    def _follow(self) -> None:
        delay = self._retry_s
        lost = False
        while not self._stopped.is_set():
            address = endpoint(self._url, self.run, every=self._every_s, since=self._since)
            try:
                with self._connect(address) as socket:
                    with self._lock:
                        self._socket = socket
                    if self._stopped.is_set():
                        return
                    if lost:
                        self._notify(f"groom is back at {self._url}; replaying what the watch missed.",
                                     {"run_id": self.run, "kind": "connection", "state": "back"})
                        lost = False
                    delay = self._retry_s
                    for frame in frames(socket):
                        self._since = frame.ts
                        self._forward(frame)
            except (OSError, TimeoutError, WebSocketException, ValueError) as exc:
                if self._stopped.is_set():
                    return
                if not lost:
                    self._notify(f"groom is unreachable at {self._url} ({exc}); the watch keeps retrying.",
                                 {"run_id": self.run, "kind": "connection", "state": "lost"})
                    lost = True
            finally:
                with self._lock:
                    self._socket = None
            self._stopped.wait(delay)
            delay = min(max(delay * 2, self._retry_s), MAX_RETRY_S)

    def _forward(self, frame: EventFrame | DigestFrame) -> None:
        if isinstance(frame, EventFrame):
            meta = {"run_id": self.run, "kind": "event", "event": frame.event.event}
            if frame.event.node:
                meta["node"] = frame.event.node
            if frame.event.gate_path:
                meta["gate_path"] = frame.event.gate_path
            self._notify(event_line(frame.event), meta)
        else:
            self._notify(frame.summary, {"run_id": self.run, "kind": "digest", "quiet": str(frame.quiet).lower()})


class Channel:
    """The MCP side: answers the session's requests and owns the watches whose frames it pushes."""

    def __init__(self, url: str, send: Send, connect: Connect = _connect, retry_s: float = 1.0) -> None:
        self._url = url
        self._send = send
        self._connect = connect
        self._retry_s = retry_s
        self._watches: dict[str, Watch] = {}

    def notify(self, content: str, meta: dict[str, str]) -> None:
        self._send({
            "jsonrpc": "2.0", "method": "notifications/claude/channel",
            "params": {"content": content, "meta": meta},
        })

    def serve(self, lines: Iterable[str]) -> None:
        try:
            for line in lines:
                if line.strip():
                    self.handle(json.loads(line))
        finally:
            self.close()

    def close(self) -> None:
        for watch in list(self._watches.values()):
            watch.stop()
        self._watches.clear()

    def handle(self, message: dict[str, Any]) -> None:
        if "id" not in message or "method" not in message:
            return
        method = message["method"]
        params = message.get("params") or {}
        if method == "initialize":
            result: dict[str, Any] = {
                "protocolVersion": params.get("protocolVersion") or PROTOCOL_VERSION,
                "capabilities": {"experimental": {"claude/channel": {}}, "tools": {}},
                "serverInfo": {"name": "groom", "version": _server_version()},
                "instructions": INSTRUCTIONS,
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": [WATCH_TOOL]}
        elif method == "tools/call":
            result = self._call(params.get("name", ""), params.get("arguments") or {})
        else:
            self._send({"jsonrpc": "2.0", "id": message["id"],
                        "error": {"code": -32601, "message": f"method not found: {method}"}})
            return
        self._send({"jsonrpc": "2.0", "id": message["id"], "result": result})

    def _call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name != "watch":
            return _tool_result(f"unknown tool: {name}", error=True)
        run = str(arguments.get("run_id") or "").strip()
        if not run:
            return _tool_result("watch needs a run_id.", error=True)
        previous = self._watches.pop(run, None)
        if previous is not None:
            previous.stop()
        if arguments.get("stop"):
            return _tool_result(f"stopped watching {run}." if previous else f"{run} was not watched.")
        every_min = float(arguments.get("every_minutes") or DEFAULT_EVERY_MIN)
        if every_min < 1:
            return _tool_result("every_minutes must be at least 1.", error=True)
        watch = Watch(url=self._url, run=run, every_s=every_min * 60, notify=self.notify,
                      connect=self._connect, retry_s=self._retry_s)
        self._watches[run] = watch
        watch.start()
        return _tool_result(
            f"watching {run} on {self._url}: events as they fire, a digest every {every_min:g} min. "
            f'They arrive as <channel source="groom" run_id="{run}">. The first digest comes right away; '
            "if none arrives, this session was not started with --dangerously-load-development-channels server:groom."
        )


def _tool_result(text: str, *, error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": error}


def run(url: str) -> None:
    """Serve MCP over stdin/stdout until the session closes stdin."""
    lock = threading.Lock()

    def send(message: dict[str, Any]) -> None:
        with lock:
            sys.stdout.write(json.dumps(message) + "\n")
            sys.stdout.flush()

    Channel(url, send).serve(sys.stdin)
