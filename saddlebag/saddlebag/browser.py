"""Typing a stored secret into a live browser, over the Chrome DevTools Protocol."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from websockets.sync.client import connect

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "http://127.0.0.1:9222"

TIMEOUT_SECONDS = 15.0

LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})


class BrowserError(RuntimeError):
    """The browser could not be reached, or could not be made to accept the value."""


@dataclass(frozen=True)
class Target:
    """One inspectable page in the browser."""

    id: str
    url: str
    title: str
    websocket_url: str


class CdpSession(Protocol):
    """One command channel to a page."""

    def send(self, method: str, params: dict[str, Any]) -> dict[str, Any]: ...


class WebSocketSession:
    """A :class:`CdpSession` over the page's debugger WebSocket."""

    def __init__(self, websocket_url: str) -> None:
        self._socket = connect(websocket_url, open_timeout=TIMEOUT_SECONDS, max_size=None)
        self._next_id = 0

    def send(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._next_id += 1
        message_id = self._next_id
        self._socket.send(json.dumps({"id": message_id, "method": method, "params": params}))
        while True:
            frame = json.loads(self._socket.recv(timeout=TIMEOUT_SECONDS))
            if frame.get("id") != message_id:
                continue
            if "error" in frame:
                raise BrowserError(f"{method} failed: {frame['error'].get('message', frame['error'])}")
            return frame.get("result", {})

    def close(self) -> None:
        self._socket.close()


def require_loopback(endpoint: str) -> None:
    """Refuse an endpoint that is not on this machine."""
    host = urllib.parse.urlparse(endpoint).hostname
    if host is None or host.lower() not in LOOPBACK_HOSTS:
        raise BrowserError(
            f"refusing to send a secret to non-loopback CDP endpoint {endpoint!r}. "
            "A DevTools port grants full control of the browser and is never "
            "authenticated; saddlebag will only talk to one on this machine."
        )


def list_targets(endpoint: str) -> tuple[Target, ...]:
    """Every inspectable page the browser is showing."""
    require_loopback(endpoint)
    url = endpoint.rstrip("/") + "/json/list"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - loopback-checked above
            payload = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise BrowserError(
            f"no browser answering at {endpoint}: {exc}. Start one with "
            "--remote-debugging-port, e.g. "
            "`chromium --remote-debugging-port=9222 --user-data-dir=/tmp/qa-profile`"
        ) from exc
    return tuple(
        Target(
            id=entry.get("id", ""),
            url=entry.get("url", ""),
            title=entry.get("title", ""),
            websocket_url=entry.get("webSocketDebuggerUrl", ""),
        )
        for entry in payload
        if entry.get("type") == "page" and entry.get("webSocketDebuggerUrl")
    )


def select_target(targets: tuple[Target, ...], url_contains: str | None) -> Target:
    """The one page to type into."""
    if not targets:
        raise BrowserError("the browser has no inspectable pages open")
    matches = (
        targets
        if url_contains is None
        else tuple(t for t in targets if url_contains in t.url)
    )
    if not matches:
        listing = "\n".join(f"  - {t.url}" for t in targets)
        raise BrowserError(f"no open page's URL contains {url_contains!r}. Open pages:\n{listing}")
    if len(matches) > 1:
        listing = "\n".join(f"  - {t.url}" for t in matches)
        raise BrowserError(
            f"{len(matches)} pages match {url_contains!r}; narrow it so the target is "
            f"unambiguous:\n{listing}"
        )
    return next(iter(matches))


_FOCUS = """
(() => {
  const el = document.querySelector(%s);
  if (!el) return { found: false };
  el.focus();
  if (typeof el.select === 'function') el.select();
  return {
    found: true,
    editable: el.isContentEditable || ['INPUT', 'TEXTAREA'].includes(el.tagName),
    tag: el.tagName,
    type: el.getAttribute('type'),
  };
})()
"""

_LENGTH = """
(() => {
  const el = document.querySelector(%s);
  if (!el) return -1;
  return (el.isContentEditable ? el.textContent : el.value || '').length;
})()
"""


def _evaluate(session: CdpSession, expression: str) -> Any:
    result = session.send(
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True, "awaitPromise": True},
    )
    if "exceptionDetails" in result:
        details = result["exceptionDetails"]
        raise BrowserError(f"page script failed: {details.get('text', details)}")
    return result.get("result", {}).get("value")


def fill(session: CdpSession, selector: str, value: str) -> int:
    """Type ``value`` into ``selector`` on an already-open page."""
    selector_literal = json.dumps(selector)
    found = _evaluate(session, _FOCUS % selector_literal)
    if not isinstance(found, dict) or not found.get("found"):
        raise BrowserError(f"no element matches {selector!r} on that page")
    if not found.get("editable"):
        raise BrowserError(
            f"{selector!r} matches a <{str(found.get('tag', '?')).lower()}>, which cannot "
            "hold typed text; name the input itself"
        )

    session.send("Input.insertText", {"text": value})

    length = _evaluate(session, _LENGTH % selector_literal)
    if not isinstance(length, int) or length <= 0:
        raise BrowserError(
            f"{selector!r} is still empty after the insert — the field is probably "
            "read-only, or the page replaced it while it was being filled"
        )
    if length != len(value):
        logger.warning(
            "%s holds %d characters after inserting %d — the field may be masked, "
            "truncating or reformatting",
            selector,
            length,
            len(value),
        )
    return length
