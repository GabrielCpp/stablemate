"""`groom channel`: the MCP handshake a Claude Code session sees, the watch that pushes a run's outbox and inbox into it, and the reply that goes back."""
from __future__ import annotations

import json
import queue
import threading
from collections.abc import Iterator
from typing import Any

import pytest
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

from groom.attention import AttentionEvent, DigestFrame, EventFrame, Standing, Window
from groom.channel import Channel


class FakeSocket:
    def __init__(self, frames: list[str], *, drop: bool = False) -> None:
        self._frames = list(frames)
        self._drop = drop
        self.closed = threading.Event()

    def recv(self) -> str:
        if self._frames:
            return self._frames.pop(0)
        if self._drop:
            raise ConnectionClosedError(None, None)
        self.closed.wait()
        raise ConnectionClosedOK(None, None)

    def close(self) -> None:
        self.closed.set()

    def __enter__(self) -> FakeSocket:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class FakeGroom:
    def __init__(self, *script: FakeSocket | Exception) -> None:
        self._script = list(script)
        self.addresses: list[str] = []

    def __call__(self, address: str) -> FakeSocket:
        self.addresses.append(address)
        item = self._script.pop(0) if self._script else FakeSocket([])
        if isinstance(item, Exception):
            raise item
        return item


def _event(ts: float, event: str = "blocked", **fields: str) -> str:
    return EventFrame(seq=1, ts=ts, event=AttentionEvent.model_validate({"run_id": "acme", "event": event, **fields})).model_dump_json()


def _digest(ts: float, summary: str) -> str:
    return DigestFrame(
        seq=2, ts=ts, since=ts - 60, until=ts, quiet=True, summary=summary, standing=Standing(), window=Window(),
    ).model_dump_json()


class FakeMail:
    def __init__(self, *inboxes: list[dict[str, Any]], gate: dict[str, Any] | None = None,
                 answered: dict[str, Any] | None = None) -> None:
        self._inboxes = list(inboxes) or [[]]
        self.gate = gate or {"found": False}
        self.answered = answered or {"ok": True, "message": "answered over the run's control socket"}
        self.answers: list[tuple[str, str, str]] = []
        self.left: list[tuple[str, str]] = []

    def inbox(self, run: str) -> list[dict[str, Any]]:
        return self._inboxes.pop(0) if len(self._inboxes) > 1 else self._inboxes[0]

    def outbox(self, run: str) -> dict[str, Any]:
        return self.gate

    def answer(self, run: str, gate_path: str, text: str) -> dict[str, Any]:
        self.answers.append((run, gate_path, text))
        return self.answered

    def leave(self, run: str, text: str) -> dict[str, Any]:
        self.left.append((run, text))
        return {"ok": True, "message": {"id": "m1", "body": text, "at": "2026-11-18T22:00:00+00:00"}}


class Sink:
    def __init__(self) -> None:
        self.replies: queue.Queue[dict[str, Any]] = queue.Queue()
        self.pushes: queue.Queue[dict[str, Any]] = queue.Queue()

    def __call__(self, message: dict[str, Any]) -> None:
        (self.replies if "id" in message else self.pushes).put(message)

    def empty(self) -> bool:
        return self.replies.empty() and self.pushes.empty()


@pytest.fixture
def sent() -> Sink:
    return Sink()


@pytest.fixture
def channels() -> Iterator[list[Channel]]:
    made: list[Channel] = []
    yield made
    for channel in made:
        channel.close()


def _channel(groom: FakeGroom, sent: Sink, channels: list[Channel], mail: FakeMail | None = None) -> Channel:
    channel = Channel("http://127.0.0.1:8787", sent, connect=groom, mail=mail or FakeMail(), retry_s=0)
    channels.append(channel)
    return channel


def _call(channel: Channel, sent: Sink, method: str, params: dict[str, Any]) -> dict[str, Any]:
    channel.handle({"jsonrpc": "2.0", "id": 7, "method": method, "params": params})
    return sent.replies.get(timeout=30)


def _pushed(sent: Sink) -> dict[str, Any]:
    message = sent.pushes.get(timeout=30)
    assert message["method"] == "notifications/claude/channel"
    return message["params"]


def test_initialize_declares_the_claude_channel_capability(sent: Sink, channels: list[Channel]) -> None:
    channel = _channel(FakeGroom(), sent, channels)
    result = _call(channel, sent, "initialize", {"protocolVersion": "2025-03-26"})["result"]
    assert result["protocolVersion"] == "2025-03-26"
    assert result["capabilities"]["experimental"] == {"claude/channel": {}}
    assert result["capabilities"]["tools"] == {}
    assert result["serverInfo"]["name"] == "groom"
    assert "watch tool" in result["instructions"]


def test_the_tools_are_watch_and_reply(sent: Sink, channels: list[Channel]) -> None:
    channel = _channel(FakeGroom(), sent, channels)
    tools = _call(channel, sent, "tools/list", {})["result"]["tools"]
    assert [(tool["name"], tool["inputSchema"]["required"]) for tool in tools] == [
        ("watch", ["run_id"]), ("reply", ["run_id", "text"]),
    ]


def test_an_unknown_request_is_method_not_found(sent: Sink, channels: list[Channel]) -> None:
    channel = _channel(FakeGroom(), sent, channels)
    assert _call(channel, sent, "resources/list", {})["error"]["code"] == -32601


def test_a_notification_from_the_session_gets_no_answer(sent: Sink, channels: list[Channel]) -> None:
    channel = _channel(FakeGroom(), sent, channels)
    channel.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert sent.empty()


def test_watch_without_a_run_is_a_tool_error(sent: Sink, channels: list[Channel]) -> None:
    groom = FakeGroom()
    channel = _channel(groom, sent, channels)
    result = _call(channel, sent, "tools/call", {"name": "watch", "arguments": {"run_id": " "}})["result"]
    assert result["isError"] is True
    assert groom.addresses == []


def test_watch_pushes_each_event_and_digest_with_its_run_and_kind(
    sent: Sink, channels: list[Channel],
) -> None:
    groom = FakeGroom(FakeSocket([
        _event(100.0, node="plan", question="Ship it?", gate_path="/runs/acme/gate.md"),
        _digest(160.0, "acme: quiet, parked at plan"),
    ]))
    channel = _channel(groom, sent, channels)
    result = _call(channel, sent, "tools/call", {"name": "watch", "arguments": {"run_id": "acme", "every_minutes": 5}})
    assert result["result"]["isError"] is False
    event = _pushed(sent)
    assert event["meta"] == {
        "run_id": "acme", "kind": "event", "event": "blocked", "node": "plan", "gate_path": "/runs/acme/gate.md",
    }
    assert "Ship it?" in event["content"]
    digest = _pushed(sent)
    assert digest == {"content": "acme: quiet, parked at plan", "meta": {"run_id": "acme", "kind": "digest", "quiet": "true"}}
    assert "run=acme" in groom.addresses[0]
    assert "every=300.0" in groom.addresses[0]
    assert "since" not in groom.addresses[0]


def test_a_lost_feed_says_so_once_and_resumes_after_the_last_frame(
    sent: Sink, channels: list[Channel],
) -> None:
    groom = FakeGroom(
        FakeSocket([_event(100.0)], drop=True),
        ConnectionRefusedError("refused"),
        FakeSocket([_event(150.0, event="ended", terminal="done")]),
    )
    channel = _channel(groom, sent, channels)
    _call(channel, sent, "tools/call", {"name": "watch", "arguments": {"run_id": "acme"}})
    kinds = [(pushed["meta"]["kind"], pushed["meta"].get("event") or pushed["meta"].get("state")) for pushed in
             (_pushed(sent) for _ in range(4))]
    assert kinds == [("event", "blocked"), ("connection", "lost"), ("connection", "back"), ("event", "ended")]
    assert all("since=100.0" in address for address in groom.addresses[1:3])


def test_stop_closes_the_feed_and_pushes_nothing_more(sent: Sink, channels: list[Channel]) -> None:
    live = FakeSocket([_event(100.0)])
    groom = FakeGroom(live)
    channel = _channel(groom, sent, channels)
    _call(channel, sent, "tools/call", {"name": "watch", "arguments": {"run_id": "acme"}})
    _pushed(sent)
    result = _call(channel, sent, "tools/call", {"name": "watch", "arguments": {"run_id": "acme", "stop": True}})
    assert result["result"]["content"][0]["text"] == "stopped watching acme."
    assert live.closed.is_set()
    assert sent.empty()
    assert len(groom.addresses) == 1


def test_serve_answers_each_line_and_stops_every_watch_at_end_of_input(
    sent: Sink, channels: list[Channel],
) -> None:
    live = FakeSocket([])
    channel = _channel(FakeGroom(live), sent, channels)
    lines = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
        "",
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": "watch", "arguments": {"run_id": "acme"}}}),
    ]
    channel.serve(line + "\n" for line in lines)
    answered = [sent.replies.get(timeout=30)["id"] for _ in range(2)]
    assert answered == [1, 2]
    assert live.closed.is_set()


def _failure(message_id: str, reply: str = "") -> dict[str, Any]:
    return {"id": message_id, "body": "failure_class: Timeout\nnode: plan", "at": "t", "kind": "failure",
            "reply": reply}


def _note(message_id: str, reply: str = "") -> dict[str, Any]:
    return {"id": message_id, "body": "skip the docs pass", "at": "t", "reply": reply}


def test_a_message_the_run_left_reaches_the_session_once(sent: Sink, channels: list[Channel]) -> None:
    mail = FakeMail([_failure("f0", reply="seen"), _failure("f1")])
    channel = _channel(FakeGroom(FakeSocket([_digest(100.0, "first"), _digest(160.0, "second")])), sent, channels, mail)
    _call(channel, sent, "tools/call", {"name": "watch", "arguments": {"run_id": "acme"}})
    pushed = [_pushed(sent) for _ in range(3)]
    assert [p["meta"]["kind"] for p in pushed] == ["digest", "inbox", "digest"]
    assert pushed[1] == {
        "content": "failure_class: Timeout\nnode: plan",
        "meta": {"run_id": "acme", "kind": "inbox", "inbox_kind": "failure", "message_id": "f1"},
    }
    assert sent.pushes.empty()


def test_the_runs_reply_to_a_session_message_arrives_once_it_lands(sent: Sink, channels: list[Channel]) -> None:
    mail = FakeMail(
        [_note("old", reply="done"), _note("m1")],
        [_note("old", reply="done"), _note("m1", reply="noted, skipping docs")],
    )
    frames = [_digest(100.0, "first"), _digest(160.0, "second"), _digest(220.0, "third")]
    channel = _channel(FakeGroom(FakeSocket(frames)), sent, channels, mail)
    _call(channel, sent, "tools/call", {"name": "watch", "arguments": {"run_id": "acme"}})
    pushed = [_pushed(sent) for _ in range(4)]
    assert [p["meta"]["kind"] for p in pushed] == ["digest", "digest", "inbox", "digest"]
    assert pushed[2]["meta"] == {"run_id": "acme", "kind": "inbox", "in_reply_to": "m1"}
    assert pushed[2]["content"].startswith("noted, skipping docs")
    assert sent.pushes.empty()


def test_a_blocked_event_without_a_gate_path_takes_the_outbox_gate(sent: Sink, channels: list[Channel]) -> None:
    mail = FakeMail(gate={"found": True, "file_path": "/runs/acme/decision.md", "question": "Which backend?"})
    channel = _channel(FakeGroom(FakeSocket([_event(100.0)])), sent, channels, mail)
    _call(channel, sent, "tools/call", {"name": "watch", "arguments": {"run_id": "acme"}})
    event = _pushed(sent)
    assert event["meta"]["gate_path"] == "/runs/acme/decision.md"
    assert "Which backend?" in event["content"]


def test_reply_with_a_gate_path_answers_that_gate(sent: Sink, channels: list[Channel]) -> None:
    mail = FakeMail()
    channel = _channel(FakeGroom(), sent, channels, mail)
    result = _call(channel, sent, "tools/call", {"name": "reply", "arguments": {
        "run_id": "acme", "text": "sqlite", "gate_path": "/runs/acme/decision.md",
    }})["result"]
    assert result["isError"] is False
    assert mail.answers == [("acme", "/runs/acme/decision.md", "sqlite")]
    assert mail.left == []


def test_a_refused_answer_is_a_tool_error(sent: Sink, channels: list[Channel]) -> None:
    mail = FakeMail(answered={"ok": False, "message": "already answered"})
    channel = _channel(FakeGroom(), sent, channels, mail)
    result = _call(channel, sent, "tools/call", {"name": "reply", "arguments": {
        "run_id": "acme", "text": "sqlite", "gate_path": "/runs/acme/decision.md",
    }})["result"]
    assert result["isError"] is True
    assert "already answered" in result["content"][0]["text"]


def test_reply_without_a_gate_leaves_an_inbox_message(sent: Sink, channels: list[Channel]) -> None:
    mail = FakeMail()
    channel = _channel(FakeGroom(), sent, channels, mail)
    result = _call(channel, sent, "tools/call", {"name": "reply", "arguments": {
        "run_id": "acme", "text": "skip the docs pass",
    }})["result"]
    assert result["isError"] is False
    assert mail.left == [("acme", "skip the docs pass")]
    assert mail.answers == []
    assert "m1" in result["content"][0]["text"]


def test_reply_without_text_is_a_tool_error(sent: Sink, channels: list[Channel]) -> None:
    mail = FakeMail()
    channel = _channel(FakeGroom(), sent, channels, mail)
    result = _call(channel, sent, "tools/call", {"name": "reply", "arguments": {"run_id": "acme", "text": " "}})
    assert result["result"]["isError"] is True
    assert mail.left == [] and mail.answers == []
