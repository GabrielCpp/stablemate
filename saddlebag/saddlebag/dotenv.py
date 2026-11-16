"""Reading and masking a dotenv file line by line. Pure and stdlib only."""

from __future__ import annotations

import re
from dataclasses import dataclass

from saddlebag._vendor.stablemate_core.dotenv import assignment

MARK = "[REDACTED]"


@dataclass(frozen=True)
class Line:
    """One line of a dotenv: its text, and its key and unquoted value when it assigns one."""

    raw: str
    key: str | None
    value: str | None


def _line(raw: str) -> Line:
    found = assignment(raw)
    if found is None:
        return Line(raw, None, None)
    return Line(raw, found[0], found[1])


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


_BARE = re.compile(r"[^\s#'\"\\$`]*")


def quote(value: str) -> str:
    """*value* written so that a dotenv reader gives it back unchanged. Raises ValueError when no quoting can."""
    if "\n" in value or "\r" in value:
        raise ValueError("a value cannot span lines")
    if _BARE.fullmatch(value):
        return value
    if "'" not in value:
        return f"'{value}'"
    if not any(char in value for char in "\"\\$`"):
        return f'"{value}"'
    raise ValueError("a value cannot hold both quote kinds")


def _tail(rest: str) -> str:
    """What follows the value in *rest*, the text after ``=``: a closing quote's trailing comment, or an unquoted value's."""
    stripped = rest.lstrip()
    if stripped[:1] in ("'", '"'):
        end = stripped.find(stripped[0], 1)
        return stripped[end + 1 :].rstrip("\r\n") if end > 0 else ""
    comment = re.search(r"\s+#.*$", rest.rstrip("\r\n"))
    return comment.group(0) if comment else ""


def assign(text: str, key: str, value: str) -> tuple[str, bool]:
    """*text* with every assignment of *key* set to *value*, or the assignment appended; and whether *key* was there."""
    written = quote(value)
    lines = text.splitlines(keepends=True)
    found = False
    for index, raw in enumerate(lines):
        line = _line(raw.rstrip("\r\n"))
        if line.key != key:
            continue
        match = re.match(rf"(\s*(?:export\s+)?{re.escape(key)}\s*=[ \t]*)(.*)", raw.rstrip("\r\n"))
        if match is None:
            continue
        ending = raw[len(raw.rstrip("\r\n")) :]
        lines[index] = f"{match.group(1)}{written}{_tail(match.group(2))}{ending}"
        found = True
    if not found:
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines.append("\n")
        lines.append(f"{key}={written}\n")
    return "".join(lines), found
