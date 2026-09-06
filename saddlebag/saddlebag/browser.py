"""Typing a stored secret into a live browser, over the Chrome DevTools Protocol.

This is the verb that makes the pool usable for the thing a test identity is *for*:
signing in. Until it existed, an agent driving a browser had two options and both
were wrong — read the password into its own context and type it (the secret is then
in a transcript, a log and a process's memory), or render it to a file and have the
harness read it (the secret is then on disk, and the file outlives the login).

``fill`` is the third option. Saddlebag opens the store, connects to a browser that
is *already* running under the caller's control, and types the value into a selector
the caller names. The caller says **where**; saddlebag supplies **what**, and the
value never crosses back — the only thing this module returns about a secret is how
many characters it typed.

That keeps the vault's opacity guarantee intact. ``fill`` prints no secret, logs no
secret and returns no secret, exactly like every other command except ``env render``.
The browser ends up holding the value, which is the entire point: it is the one place
the password is supposed to arrive.

**The endpoint is trusted, and must be local.** Anything that can reach a CDP port
already has total control of that browser — it can read every page, every cookie and
every keystroke. Saddlebag therefore refuses a non-loopback endpoint rather than
letting a typo mail a password to a host on the network.
"""

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

#: Where Chromium listens when started with --remote-debugging-port=9222.
DEFAULT_ENDPOINT = "http://127.0.0.1:9222"

#: How long to wait for the browser to answer one CDP command.
TIMEOUT_SECONDS = 15.0

#: Hosts a CDP endpoint may name. See the module docstring.
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
    """One command channel to a page.

    A protocol rather than a concrete class because it is the seam the tests
    substitute at: a fake session records the commands a fill issues and answers
    them, so the fill logic is exercised without a browser.
    """

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
        # CDP interleaves unsolicited events with command replies on the same socket, so
        # the reply to *this* command is the next frame carrying *this* id — not simply
        # the next frame.
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
    """Refuse an endpoint that is not on this machine.

    A remote CDP port is not a deployment option to support — it is a password
    leaving the host in cleartext, addressed to whoever answers.
    """
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
    """The one page to type into.

    Ambiguity is an error rather than a guess. Typing a password into whichever tab
    happened to sort first is the kind of mistake that is silent at the time and
    unrecoverable afterwards — the value has been entered into some page nobody
    chose, and the operator finds out from a login that did not happen.
    """
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
    # Taken through the iterator rather than by index: the two checks above have already
    # established that exactly one is left, but a length comparison is not something a
    # type checker narrows a tuple by, so indexing reads as possibly-out-of-range there.
    return next(iter(matches))


# Focuses the field and selects whatever it already holds, so the insert that follows
# replaces the content rather than appending to a half-typed value. Reports what it
# found so a wrong selector fails here, named, instead of silently typing into nothing.
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

# Reads back the length only. Returning the value would hand the secret to the caller
# and undo the whole point of typing it here.
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
    """Type ``value`` into ``selector`` on an already-open page. Returns its length.

    ``Input.insertText`` rather than a scripted assignment to ``el.value``: a direct
    assignment does not raise the events a framework listens for, so a React- or
    Vue-controlled field accepts the text visually and then submits the empty string
    its state still holds. insertText enters the value the way a paste does, above the
    page, so every listener sees what it would see from a person.
    """
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
    # Length, never the value, and never a comparison the caller could bisect a
    # secret with. A mismatch is worth reporting because it means the field
    # transformed or truncated the input, which a login will fail on later.
    if length != len(value):
        logger.warning(
            "%s holds %d characters after inserting %d — the field may be masked, "
            "truncating or reformatting",
            selector,
            length,
            len(value),
        )
    return length
