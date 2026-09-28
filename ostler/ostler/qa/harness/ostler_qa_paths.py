"""The document-path grammar every reader of a JSON document shares: its steps, and how a path walks a document."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


class Wild:
    """The `[*]` segment: every element of a list, every value of an object."""

    def __repr__(self) -> str:
        return "[*]"


WILD = Wild()


@dataclass(frozen=True)
class Filter:
    """The `[?(@.key==value)]` segment: the elements whose `key` holds `value`."""

    key: str
    value: Any

    def __repr__(self) -> str:
        return f"[?(@.{self.key}=={json.dumps(self.value)})]"


PathStep = str | int | Wild | Filter

_FILTER = re.compile(
    r"\[\?\(@\.(?P<key>[^=\s)]+)\s*==\s*"
    r"(?P<value>'[^']*'|\"[^\"]*\"|-?\d+(?:\.\d+)?|true|false|null)\s*\)\]"
)


def path_steps(path: str) -> list[PathStep]:
    """The segments of a path, in the one grammar every reader of a document path shares."""
    steps: list[PathStep] = []
    text = path.strip()
    if text.startswith("$"):
        text = text[1:]
    pos = 0
    while pos < len(text):
        char = text[pos]
        if char == ".":
            pos += 1
            continue
        if char == "[":
            if text.startswith("[*]", pos):
                steps.append(WILD)
                pos += 3
                continue
            hit = _FILTER.match(text, pos)
            if hit is not None:
                steps.append(Filter(hit.group("key"), json.loads(hit.group("value").replace("'", '"'))))
                pos = hit.end()
                continue
            close = text.find("]", pos)
            if close == -1:
                raise ValueError(f"json path {path!r}: '[' at {pos} is never closed")
            inner = text[pos + 1 : close]
            steps.append(int(inner) if inner.isdigit() else inner)
            pos = close + 1
            continue
        nxt = len(text)
        for stop in (".", "["):
            found = text.find(stop, pos)
            if found != -1:
                nxt = min(nxt, found)
        steps.append(text[pos:nxt])
        pos = nxt
    return steps


def _step_into(current: Any, step: str | int) -> tuple[bool, Any]:
    if isinstance(current, Mapping):
        key = str(step) if isinstance(step, int) else step
        return (True, current[key]) if key in current else (False, None)
    if isinstance(current, (list, tuple)):
        if isinstance(step, int):
            index = step
        elif step.isdigit():
            index = int(step)
        else:
            return False, None
        return (True, current[index]) if index < len(current) else (False, None)
    return False, None


def _selected(current: Any, step: Wild | Filter) -> list[Any]:
    if isinstance(current, Mapping):
        candidates = list(current.values())
    elif isinstance(current, (list, tuple)):
        candidates = list(current)
    else:
        return []
    if isinstance(step, Wild):
        return candidates
    chosen = []
    for item in candidates:
        ok, held = resolve_path(item, step.key)
        if ok and scalar_equal(held, step.value):
            chosen.append(item)
    return chosen


def resolve_path(document: Any, path: str) -> tuple[bool, Any]:
    """Walk `path` into `document`: whether it resolved, and to what."""
    steps = path_steps(path)
    current: Any = document
    projected = False
    for step in steps:
        if isinstance(step, (Wild, Filter)):
            if projected:
                current = [item for element in current for item in _selected(element, step)]
            else:
                current = _selected(current, step)
                projected = True
            continue
        if projected:
            kept = []
            for element in current:
                ok, value = _step_into(element, step)
                if ok:
                    kept.append(value)
            current = kept
            continue
        ok, current = _step_into(current, step)
        if not ok:
            return False, None
    if projected:
        return bool(current), current
    return True, current


def is_projection(path: str) -> bool:
    return any(isinstance(step, (Wild, Filter)) for step in path_steps(path))


def scalar_equal(observed: Any, expected: Any) -> bool:
    """`json_path(equals=)` against what the document holds, typed the way JSON types it."""
    if isinstance(expected, bool) or isinstance(observed, bool):
        return isinstance(observed, bool) and isinstance(expected, bool) and observed is expected
    if isinstance(expected, (int, float)):
        return isinstance(observed, (int, float)) and observed == expected
    if isinstance(expected, str):
        return isinstance(observed, str) and observed == expected
    return False
