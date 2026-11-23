"""``groom channel``: a stdio MCP server that carries a watched run's outbox and inbox into a Claude Code session, and the session's answers back to the run."""
from __future__ import annotations

import json
import sys
import threading
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Protocol
from urllib.parse import quote

from websockets.exceptions import WebSocketException
from websockets.sync.client import connect

from groom.attention import DigestFrame, EventFrame
from groom.wait import endpoint, event_line, frames

PROTOCOL_VERSION = "2025-06-18"
DEFAULT_EVERY_MIN = 30.0
MAX_RETRY_S = 30.0
HTTP_TIMEOUT_S = 10.0

INSTRUCTIONS = (
    "groom carries workhorse runs to this session and this session's answers back to them. "
    "Call the watch tool with a run_id to follow a run. "
    'Updates arrive as <channel source="groom" run_id="..." kind="...">. '
    "kind=event is an attention event the moment it fires: blocked, ended, stuck, stalled, gave-up, churn, "
    "watchdog, died, waiting or compact-loop. The event attribute names it. A blocked event is a question from the run's outbox: "
    "its gate_path attribute names the gate, and the reply tool with that gate_path answers it. "
    "kind=inbox is a message the run left for its operator, such as a failure handoff (inbox_kind=failure), or the "
    "run's reply to a message this session sent (in_reply_to names it). "
    "kind=digest is the periodic summary of the run, sent even when nothing happened. "
    "kind=connection reports that groom became unreachable or came back. After a loss the watch replays what it "
    "missed. The reply tool without gate_path leaves a message in the run's inbox, which the run reads at its "
    "next poll point."
)

WATCH_TOOL: dict[str, Any] = {
    "name": "watch",
    "description": (
        "Push a workhorse run's outbox and inbox into this session: each attention event as it fires, each "
        "message the run leaves for its operator, and a digest on an interval. Call again with stop=true to end "
        "the watch."
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

REPLY_TOOL: dict[str, Any] = {
    "name": "reply",
    "description": (
        "Send text to a workhorse run. With gate_path it answers that operator gate, and the parked run resumes. "
        "Without gate_path it leaves a message in the run's inbox."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "run_id": {"type": "string", "description": "Exact run_id to send to."},
            "text": {"type": "string", "description": "The answer or the message."},
            "gate_path": {
                "type": "string",
                "description": "The gate_path of the blocked event being answered. Omit it to leave an inbox message.",
            },
        },
        "required": ["run_id", "text"],
    },
}


class FeedSocket(Protocol):
    def recv(self) -> str | bytes: ...

    def close(self) -> None: ...


class RunMail(Protocol):
    def inbox(self, run: str) -> list[dict[str, Any]]: ...

    def outbox(self, run: str) -> dict[str, Any]: ...

    def answer(self, run: str, gate_path: str, text: str) -> dict[str, Any]: ...

    def leave(self, run: str, text: str) -> dict[str, Any]: ...


Connect = Callable[[str], AbstractContextManager[FeedSocket]]
Send = Callable[[dict[str, Any]], None]
Notify = Callable[[str, dict[str, str]], None]


def _connect(address: str) -> AbstractContextManager[FeedSocket]:
    return connect(address, open_timeout=5, close_timeout=1, ping_interval=20, ping_timeout=20)


def _server_version() -> str:
    try:
        return version("stablemate-groom")
    except PackageNotFoundError:
        return "0"


class GroomMail:
    """A run's outbox and inbox over groom's HTTP API, the same routes ``control questions/answer`` and ``inbox`` name."""

    def __init__(self, url: str) -> None:
        self._url = url.rstrip("/")

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            f"{self._url}{path}", data=data, method=method, headers={"content-type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:
            return json.loads(response.read())

    def _run(self, run: str) -> str:
        return f"/api/run/{quote(run, safe='')}"

    def inbox(self, run: str) -> list[dict[str, Any]]:
        return list(self._call("GET", f"{self._run(run)}/inbox?include_all=true").get("messages") or [])

    def outbox(self, run: str) -> dict[str, Any]:
        return self._call("GET", f"{self._run(run)}/outbox")

    def answer(self, run: str, gate_path: str, text: str) -> dict[str, Any]:
        return self._call("POST", f"{self._run(run)}/outbox", {"file_path": gate_path, "answer": text})

    def leave(self, run: str, text: str) -> dict[str, Any]:
        return self._call("POST", f"{self._run(run)}/inbox", {"body": text})


MAIL_ERRORS = (OSError, ValueError, urllib.error.URLError)


class Inbox:
    """What a run's inbox holds that the session has not been told: a message the run left, or the run's reply to one."""

    def __init__(self, run: str, mail: RunMail, notify: Notify) -> None:
        self._run = run
        self._mail = mail
        self._notify = notify
        self._seen: set[str] | None = None

    def deliver(self) -> None:
        try:
            messages = self._mail.inbox(self._run)
        except MAIL_ERRORS:
            return
        first = self._seen is None
        seen = self._seen if self._seen is not None else set()
        for message in messages:
            message_id = str(message.get("id", ""))
            kind = str(message.get("kind") or "")
            reply = str(message.get("reply") or "")
            if kind and message_id not in seen:
                seen.add(message_id)
                if not (first and reply):
                    self._notify(str(message.get("body", "")), {
                        "run_id": self._run, "kind": "inbox", "inbox_kind": kind, "message_id": message_id,
                    })
            elif not kind and reply and f"{message_id}:reply" not in seen:
                seen.add(f"{message_id}:reply")
                if not first:
                    self._notify(f"{reply}\n\n(your message: {message.get('body', '')})", {
                        "run_id": self._run, "kind": "inbox", "in_reply_to": message_id,
                    })
        self._seen = seen


class Watch:
    """One run's feed, kept connected until stopped; a reconnect asks for every frame after the last one seen."""

    def __init__(
        self, *, url: str, run: str, every_s: float, notify: Notify, mail: RunMail, connect: Connect, retry_s: float,
    ) -> None:
        self.run = run
        self._url = url
        self._every_s = every_s
        self._notify = notify
        self._mail = mail
        self._inbox = Inbox(run, mail, notify)
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
                        self._inbox.deliver()
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
        if isinstance(frame, DigestFrame):
            self._notify(frame.summary, {"run_id": self.run, "kind": "digest", "quiet": str(frame.quiet).lower()})
            return
        event = frame.event
        if event.event == "blocked" and not event.gate_path:
            try:
                gate = self._mail.outbox(self.run)
            except MAIL_ERRORS:
                gate = {}
            if gate.get("found"):
                event = event.model_copy(update={
                    "gate_path": str(gate.get("file_path", "")),
                    "question": event.question or str(gate.get("question", "")),
                })
        meta = {"run_id": self.run, "kind": "event", "event": event.event}
        if event.node:
            meta["node"] = event.node
        if event.gate_path:
            meta["gate_path"] = event.gate_path
        self._notify(event_line(event), meta)


class Channel:
    """The MCP side: answers the session's requests and owns the watches whose frames it pushes."""

    def __init__(
        self, url: str, send: Send, connect: Connect = _connect, mail: RunMail | None = None, retry_s: float = 1.0,
    ) -> None:
        self._url = url
        self._send = send
        self._connect = connect
        self._mail = mail if mail is not None else GroomMail(url)
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
            result = {"tools": [WATCH_TOOL, REPLY_TOOL]}
        elif method == "tools/call":
            result = self._call(params.get("name", ""), params.get("arguments") or {})
        else:
            self._send({"jsonrpc": "2.0", "id": message["id"],
                        "error": {"code": -32601, "message": f"method not found: {method}"}})
            return
        self._send({"jsonrpc": "2.0", "id": message["id"], "result": result})

    def _call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        run = str(arguments.get("run_id") or "").strip()
        if name not in ("watch", "reply"):
            return _tool_result(f"unknown tool: {name}", error=True)
        if not run:
            return _tool_result(f"{name} needs a run_id.", error=True)
        if name == "reply":
            return self._reply(run, str(arguments.get("text") or ""), str(arguments.get("gate_path") or "").strip())
        return self._watch(run, arguments)

    def _watch(self, run: str, arguments: dict[str, Any]) -> dict[str, Any]:
        previous = self._watches.pop(run, None)
        if previous is not None:
            previous.stop()
        if arguments.get("stop"):
            return _tool_result(f"stopped watching {run}." if previous else f"{run} was not watched.")
        every_min = float(arguments.get("every_minutes") or DEFAULT_EVERY_MIN)
        if every_min < 1:
            return _tool_result("every_minutes must be at least 1.", error=True)
        watch = Watch(url=self._url, run=run, every_s=every_min * 60, notify=self.notify, mail=self._mail,
                      connect=self._connect, retry_s=self._retry_s)
        self._watches[run] = watch
        watch.start()
        return _tool_result(
            f"watching {run} on {self._url}: events as they fire, inbox messages as they land, a digest every "
            f'{every_min:g} min. They arrive as <channel source="groom" run_id="{run}">. The first digest comes '
            "right away; if none arrives, this session was not started with "
            "--dangerously-load-development-channels server:groom."
        )

    def _reply(self, run: str, text: str, gate_path: str) -> dict[str, Any]:
        if not text.strip():
            return _tool_result("reply needs text.", error=True)
        try:
            if gate_path:
                answered = self._mail.answer(run, gate_path, text)
                return _tool_result(f"{run}: {answered.get('message', '')}", error=not answered.get("ok"))
            left = self._mail.leave(run, text)
        except MAIL_ERRORS as exc:
            return _tool_result(f"groom did not take the reply at {self._url}: {exc}", error=True)
        if not left.get("ok"):
            return _tool_result(f"{run}: {left.get('message', '')}", error=True)
        message_id = str((left.get("message") or {}).get("id", ""))
        return _tool_result(f"left message {message_id} in {run}'s inbox; the run reads it at its next poll point.")


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
