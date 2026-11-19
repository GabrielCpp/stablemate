"""`groom channel`: the MCP handshake a Claude Code session sees and the watch that pushes a run's feed into it."""
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


def _channel(groom: FakeGroom, sent: Sink, channels: list[Channel]) -> Channel:
    channel = Channel("http://127.0.0.1:8787", sent, connect=groom, retry_s=0)
    channels.append(channel)
    return channel


def _call(channel: Channel, sent: Sink, method: str, params: dict[str, Any]) -> dict[str, Any]:
    channel.handle({"jsonrpc": "2.0", "id": 7, "method": method, "params": params})
    return sent.replies.get(timeout=5)


def _pushed(sent: Sink) -> dict[str, Any]:
    message = sent.pushes.get(timeout=5)
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


def test_the_one_tool_is_watch(sent: Sink, channels: list[Channel]) -> None:
    channel = _channel(FakeGroom(), sent, channels)
    tools = _call(channel, sent, "tools/list", {})["result"]["tools"]
    assert [tool["name"] for tool in tools] == ["watch"]
    assert tools[0]["inputSchema"]["required"] == ["run_id"]


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
    answered = [sent.replies.get(timeout=5)["id"] for _ in range(2)]
    assert answered == [1, 2]
    assert live.closed.is_set()
