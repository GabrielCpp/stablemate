"""Masking secret values, as written and as tools escape them, out of a child command's output."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import threading
from collections.abc import Collection, Iterable
from types import FrameType
from typing import IO, BinaryIO
from urllib.parse import quote, quote_plus

MIN_LENGTH = 8
MARK = b"[REDACTED]"
_CHUNK = 65536
_FORWARDED = (signal.SIGINT, signal.SIGTERM)


def forms(value: str) -> frozenset[str]:
    """*value* as written, and as compose, a URL and a JSON string escape it."""
    return frozenset({
        value,
        value.replace("$", "$$"),
        quote(value, safe=""),
        quote_plus(value, safe=""),
        json.dumps(value)[1:-1],
        json.dumps(value, ensure_ascii=False)[1:-1],
    })


class Redactor:
    """Replaces every form of some values in a byte stream that arrives in pieces."""

    def __init__(self, values: Iterable[str]) -> None:
        needles = sorted({form.encode() for value in values for form in forms(value) if form}, key=len, reverse=True)
        if not needles:
            raise ValueError("a redactor needs at least one non-empty value")
        self._pattern = re.compile(b"|".join(map(re.escape, needles)))
        self._longest = len(needles[0])
        self._held = b""

    def feed(self, chunk: bytes) -> bytes:
        """The part of the stream so far that no later chunk can turn into a match, masked."""
        held = self._held + chunk
        safe = len(held) - self._longest + 1
        out = bytearray()
        pos = 0
        for match in self._pattern.finditer(held):
            if match.start() >= safe:
                break
            out += held[pos:match.start()] + MARK
            pos = match.end()
        cut = max(pos, safe)
        out += held[pos:cut]
        self._held = held[cut:]
        return bytes(out)

    def flush(self) -> bytes:
        """The rest of the stream, masked, once no chunk follows."""
        rest, self._held = self._held, b""
        return self._pattern.sub(MARK, rest)


def relay(command: list[str], env: dict[str, str], values: Collection[str]) -> int:
    """Run *command* with *env*, copy its stdout and stderr to ours with every form of *values* masked, and return its exit code."""
    child = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if child.stdout is None or child.stderr is None:
        raise RuntimeError("the child was started without pipes")
    pumps = [
        threading.Thread(target=_pump, args=(child.stdout, sys.stdout.buffer, Redactor(values))),
        threading.Thread(target=_pump, args=(child.stderr, sys.stderr.buffer, Redactor(values))),
    ]

    def forward(signum: int, _frame: FrameType | None) -> None:
        child.send_signal(signum)

    previous = {signum: signal.signal(signum, forward) for signum in _FORWARDED}
    try:
        for pump in pumps:
            pump.start()
        code = child.wait()
        for pump in pumps:
            pump.join()
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, signal.SIG_DFL if handler is None else handler)
    return 128 - code if code < 0 else code


def _pump(source: IO[bytes], sink: BinaryIO, redactor: Redactor) -> None:
    while chunk := os.read(source.fileno(), _CHUNK):
        sink.write(redactor.feed(chunk))
        sink.flush()
    sink.write(redactor.flush())
    sink.flush()
    source.close()
