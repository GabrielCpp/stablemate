"""The whys nothing written settles, one line each in `QUESTIONS.md` beside `service.py`."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from ostler.book import decisions

ENTRY = re.compile(r"^- (\w+): (.+)$")


@dataclass(frozen=True)
class Question:
    element: str
    text: str
    line: int


def load(module: str) -> list[Question]:
    path = os.path.join(os.path.dirname(decisions.directory(module)), "QUESTIONS.md")
    if not os.path.isfile(path):
        return []
    with open(path) as f:
        rows = f.read().splitlines()
    found = [(n, ENTRY.match(row.strip())) for n, row in enumerate(rows, 1)]
    return [Question(m.group(1), m.group(2).strip(), n) for n, m in found if m]
