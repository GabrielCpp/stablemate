"""Redacting known secret values — and a handful of recognisable secret *shapes* — out of an agent CLI's own output before it reaches a transcript, a checkpoint, or telemetry."""

from __future__ import annotations

import base64
import json
import re
import urllib.parse
from collections.abc import Iterable

REDACTED = "••••"

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
_HEURISTIC_MARGIN = 64


def _derived_forms(value: str) -> Iterable[str]:
    """Every literal spelling of ``value`` that might appear verbatim in a CLI's own output: the raw string, its base64 (an ``Authorization: Basic`` header), URL-encoded, and JSON-escaped (inside a quoted NDJSON string) forms."""
    yield value
    yield base64.b64encode(value.encode("utf-8")).decode("ascii")
    yield urllib.parse.quote(value, safe="")
    yield json.dumps(value)[1:-1]


class SecretRedactor:
    """Streaming filter: rewrites known secret values, and recognisable secret shapes, to ``••••`` across a sequence of text chunks of any granularity — one already newline-delimited line from ``process.py``'s reader, a raw byte read, an HTTP body fragment."""

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        needles: set[str] = set()
        for secret in secrets:
            if not secret:
                continue
            needles.update(_derived_forms(secret))
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
