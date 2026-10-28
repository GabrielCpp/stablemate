"""Reading and masking a dotenv file line by line. Pure and stdlib only."""

from __future__ import annotations

import re
from dataclasses import dataclass

MARK = "[REDACTED]"
_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*")
_EXPORT = re.compile(r"export\s+")
_COMMENT = re.compile(r"\s+#.*$")


@dataclass(frozen=True)
class Line:
    """One line of a dotenv: its text, and its key and unquoted value when it assigns one."""

    raw: str
    key: str | None
    value: str | None


def _unquote(text: str) -> str:
    if text[:1] in ("'", '"'):
        end = text.find(text[0], 1)
        return text[1:end] if end > 0 else text[1:]
    return _COMMENT.sub("", text).strip()


def _line(raw: str) -> Line:
    text = raw.strip()
    if not text or text.startswith("#"):
        return Line(raw, None, None)
    if match := _EXPORT.match(text):
        text = text[match.end():]
    key, sep, rest = text.partition("=")
    key = key.strip()
    if not sep or not _KEY.fullmatch(key):
        return Line(raw, None, None)
    return Line(raw, key, _unquote(rest.strip()))


def parse(text: str) -> list[Line]:
    """The lines of *text*, in order."""
    return [_line(raw) for raw in text.splitlines()]


def mask(line: Line) -> str:
    """The raw line with the value replaced by a mark, keeping ``export `` and ``KEY=``."""
    if line.key is None:
        return line.raw
    match = re.match(rf"(\s*(?:export\s+)?{re.escape(line.key)}\s*=\s*)", line.raw)
    if match is None:
        return line.raw
    return f"{match.group(1)}{MARK}"
