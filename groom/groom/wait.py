"""Wait silently on groom's WebSocket until a selected attention event arrives."""
from __future__ import annotations

import argparse
import json
import sys
from urllib.parse import urlsplit, urlunsplit

from websockets.exceptions import WebSocketException
from websockets.sync.client import connect

from groom.attention import (
    RULE_EVENTS,
    AttentionFrame,
    EventName,
    StateAttention,
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


def wait(url: str, run: str, until: frozenset[EventName], as_json: bool) -> None:
    """Connect once; a broken monitor fails rather than hiding a gap in coverage."""
    try:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise ValueError("GROOM_URL must be an http:// or https:// URL")
        endpoint = urlunsplit((
            "wss" if parts.scheme == "https" else "ws", parts.netloc,
            parts.path.rstrip("/") + "/ws", parts.query, "",
        ))
        with connect(endpoint, open_timeout=5, close_timeout=1) as socket:
            while True:
                # recv (not iteration) raises even on a clean server close: losing
                # the subscription without a match is a failed monitor.
                raw = socket.recv()
                frame = json.loads(raw)
                if not isinstance(frame, dict):
                    raise ValueError("expected a groom WebSocket object")
                if frame.get("type") == "state":
                    events = StateAttention.model_validate(frame).attention
                elif frame.get("type") == "attention":
                    events = AttentionFrame.model_validate(frame).events
                else:
                    continue
                for event in events:
                    if event.run_id == run and event.event in until:
                        print(event.model_dump_json() if as_json else
                              f"{event.run_id}: {event.event}"
                              f"{(' at ' + event.node) if event.node else ''}"
                              f" — {event.question or event.message or event.terminal}")
                        return
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except (OSError, TimeoutError, WebSocketException, ValueError) as exc:
        print(f"groom wait: monitoring failed at {url}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
