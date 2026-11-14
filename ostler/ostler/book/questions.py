"""The whys nothing written settles, one line each in `QUESTIONS.md` beside `service.py`."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from ostler.book import decisions

ENTRY = re.compile(r"^- (\w+): (.+)$")
NEAR = re.compile(r"^(?:[-*+]\s*)?\w+\s*:\s*\S")


@dataclass(frozen=True)
class Question:
    element: str
    text: str
    line: int


def rows(module: str) -> list[tuple[int, str]]:
    path = os.path.join(os.path.dirname(decisions.directory(module)), "QUESTIONS.md")
    if not os.path.isfile(path):
        return []
    with open(path) as f:
        return [(n, row.strip()) for n, row in enumerate(f.read().splitlines(), 1)]


def load(module: str) -> list[Question]:
    found = [(n, ENTRY.match(row)) for n, row in rows(module)]
    return [Question(m.group(1), m.group(2).strip(), n) for n, m in found if m]


def unread(module: str) -> list[int]:
    """The lines shaped like an entry that `load` does not read as one."""
    return [n for n, row in rows(module) if NEAR.match(row) and not ENTRY.match(row)]
