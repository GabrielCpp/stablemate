"""Follow one run on groom's /feed socket: wait for a selected attention event, or print every frame."""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from urllib.parse import urlencode, urlsplit, urlunsplit

from websockets.exceptions import WebSocketException
from websockets.sync.client import connect
from websockets.sync.connection import Connection

from groom.attention import (
    RULE_EVENTS,
    AttentionEvent,
    DigestFrame,
    EventFrame,
    EventName,
)


def event_names(value: str) -> frozenset[EventName]:
    names = {part.strip() for part in value.split(",")}
    known = set(RULE_EVENTS.values())
    invalid = names - known
    if invalid:
        raise argparse.ArgumentTypeError(
            f"unknown event(s): {', '.join(sorted(invalid))}; choose from {', '.join(sorted(known))}"
        )
    return frozenset(event for event in known if event in names)


def _endpoint(url: str, run: str, **params: object) -> str:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError("GROOM_URL must be an http:// or https:// URL")
    query = urlencode({"run": run, **{k: v for k, v in params.items() if v is not None}})
    return urlunsplit((
        "wss" if parts.scheme == "https" else "ws", parts.netloc,
        parts.path.rstrip("/") + "/feed", query, "",
    ))


def _event_line(event: AttentionEvent) -> str:
    return (
        f"{event.run_id}: {event.event}"
        f"{(' at ' + event.node) if event.node else ''}"
        f" — {event.question or event.message or event.terminal}"
    )


def _frames(socket: Connection) -> Iterator[EventFrame | DigestFrame]:
    while True:
        frame = json.loads(socket.recv())
        if not isinstance(frame, dict):
            raise ValueError("expected a groom WebSocket object")
        if frame.get("type") == "event":
            yield EventFrame.model_validate(frame)
        elif frame.get("type") == "digest":
            yield DigestFrame.model_validate(frame)


def wait(url: str, run: str, until: frozenset[EventName], as_json: bool) -> None:
    """Connect once; a broken monitor fails rather than hiding a gap in coverage."""
    try:
        with connect(_endpoint(url, run), open_timeout=5, close_timeout=1) as socket:
            for frame in _frames(socket):
                if isinstance(frame, EventFrame) and frame.event.run_id == run and frame.event.event in until:
                    print(frame.event.model_dump_json() if as_json else _event_line(frame.event))
                    return
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except (OSError, TimeoutError, WebSocketException, ValueError) as exc:
        print(f"groom wait: monitoring failed at {url}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def feed(url: str, run: str, every_s: float, since: float | None, as_json: bool) -> None:
    """Print one line per frame until interrupted; a lost connection fails rather than hiding a gap."""
    try:
        endpoint = _endpoint(url, run, every=every_s, since=since)
        with connect(endpoint, open_timeout=5, close_timeout=1) as socket:
            for frame in _frames(socket):
                if as_json:
                    print(frame.model_dump_json(), flush=True)
                elif isinstance(frame, DigestFrame):
                    print(frame.summary, flush=True)
                else:
                    print(_event_line(frame.event), flush=True)
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except (OSError, TimeoutError, WebSocketException, ValueError) as exc:
        print(f"groom feed: monitoring failed at {url}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
