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
