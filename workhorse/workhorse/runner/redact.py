"""Redacting known secret values — and a handful of recognisable secret *shapes* — out
of an agent CLI's own output before it reaches a transcript, a checkpoint, or telemetry.

Mounted at ``runner/process.py``'s stream loop, the one path every backend (Claude,
Codex, Copilot, OpenCode, Cline) streams through, so it protects secrets that were
never routed through saddlebag. The realistic leak is not a clever agent; it is a CLI
echoing a key in a 401 body, and that lands in the transcript, the checkpoint and
telemetry unless something sits between the pipe and all three.

Workhorse itself is never handed a policy of what counts as a secret — see
``SecretRedactor``'s ``secrets`` parameter — because a workflow's or a caller's secret
values are exactly the vocabulary the driver must stay agnostic to.
"""

from __future__ import annotations

import base64
import json
import re
import urllib.parse
from collections.abc import Iterable

REDACTED = "••••"

# Truncated-echo second net: a CLI that only prints the first N characters of a key (a
# 401 body quoting "sk-or-v1-abc...") leaks a spelling no exact-value match will ever
# catch, since the full value it was compared against never appears in the output.
# These patterns catch the recognisable shape of a handful of common provider/token
# formats instead, independent of any known secret value.
_PREFIX_PATTERNS = tuple(
    re.compile(p)
    for p in (
        r"sk-[A-Za-z0-9_-]{10,}",
        r"ghp_[A-Za-z0-9]{20,}",
        r"github_pat_[A-Za-z0-9_]{20,}",
        r"hvs\.[A-Za-z0-9]{20,}",
        r"AKIA[A-Z0-9]{12,}",
    )
)
# Held back in addition to the longest known needle so a prefix-heuristic match near a
# chunk boundary also gets a chance to complete before its half is emitted. The
# patterns above are open-ended, so this is a practical bound on plausible token
# length, not a guarantee for an arbitrarily long one.
_HEURISTIC_MARGIN = 64


def _derived_forms(value: str) -> Iterable[str]:
    """Every literal spelling of ``value`` that might appear verbatim in a CLI's own
    output: the raw string, its base64 (an ``Authorization: Basic`` header), URL-encoded,
    and JSON-escaped (inside a quoted NDJSON string) forms. All four are plain
    substrings a string replace can catch — nothing here needs to know which one a
    given CLI actually prints.
    """
    yield value
    yield base64.b64encode(value.encode("utf-8")).decode("ascii")
    yield urllib.parse.quote(value, safe="")
    yield json.dumps(value)[1:-1]  # escaped spelling, surrounding quotes stripped


class SecretRedactor:
    """Streaming filter: rewrites known secret values, and recognisable secret shapes,
    to ``••••`` across a sequence of text chunks of any granularity — one already
    newline-delimited line from ``process.py``'s reader, a raw byte read, an HTTP body
    fragment.

    A secret can straddle a chunk boundary — the tail of one chunk and the head of the
    next can together spell a value neither half contains alone — so a match cannot be
    decided chunk by chunk in isolation. ``feed`` holds back a tail long enough to
    contain any needle (plus a margin for the open-ended heuristics) on every call, and
    returns only the redacted prefix that precedes it. Call ``flush()`` once the stream
    ends to emit whatever is left; ``redact`` is the one-shot convenience for a caller
    that already has a complete unit (a full line) and wants it redacted in one call.

    Fails closed: an error while redacting a chunk drops that chunk — returns
    ``REDACTED`` rather than letting the raw text through — instead of raising into the
    caller's stream loop.

    ``secrets`` is the caller's known values, not workhorse's: a workflow or a backend
    supplies them, the same way ``env_extra`` is threaded through ``process.py`` rather
    than assembled there. An empty (the default) list still gets the prefix-heuristic
    net for free.
    """

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        needles: set[str] = set()
        for secret in secrets:
            if not secret:
                continue
            needles.update(_derived_forms(secret))
        # Longest first: a base64 form can contain a shorter needle as a substring, and
        # redacting the short one first would leave a "REDACTED<fragment>" remnant
        # instead of the whole value disappearing.
        self._needles = tuple(sorted(needles, key=len, reverse=True))
        self._tail_len = max((len(n) - 1 for n in self._needles), default=0) + _HEURISTIC_MARGIN
        self._buffer = ""

    def _rewrite(self, text: str) -> str:
        for needle in self._needles:
            text = text.replace(needle, REDACTED)
        for pattern in _PREFIX_PATTERNS:
            text = pattern.sub(REDACTED, text)
        return text

    def feed(self, chunk: str) -> str:
        try:
            self._buffer += chunk
            if len(self._buffer) <= self._tail_len:
                return ""
            emit, self._buffer = (
                self._buffer[: -self._tail_len],
                self._buffer[-self._tail_len :],
            )
            return self._rewrite(emit)
        except Exception:
            self._buffer = ""
            return REDACTED

    def flush(self) -> str:
        try:
            out = self._rewrite(self._buffer)
            self._buffer = ""
            return out
        except Exception:
            self._buffer = ""
            return REDACTED

    def redact(self, text: str) -> str:
        """Redact one complete unit — a full line — in a single call."""
        return self.feed(text) + self.flush()
