"""The document-path grammar every reader of a JSON document shares: its steps, and how a path walks a document."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

type JsonScalar = None | bool | int | float | str
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]


class Wild:
    """The `[*]` segment: every element of a list, every value of an object."""

    def __repr__(self) -> str:
        return "[*]"


WILD = Wild()


@dataclass(frozen=True)
class Filter:
    """The `[?(@.key==value)]` segment: the elements whose `key` holds `value`."""

    key: str
    value: JsonScalar

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


@dataclass(frozen=True)
class Resolved:
    """Whether a path resolved in a document, and to what."""

    found: bool
    value: JsonValue = None


def _step_into(current: JsonValue, step: str | int) -> Resolved:
    if isinstance(current, dict):
        key = str(step) if isinstance(step, int) else step
        return Resolved(True, current[key]) if key in current else Resolved(False)
    if isinstance(current, list):
        if isinstance(step, int):
            index = step
        elif step.isdigit():
            index = int(step)
        else:
            return Resolved(False)
        return Resolved(True, current[index]) if index < len(current) else Resolved(False)
    return Resolved(False)


def _selected(current: JsonValue, step: Wild | Filter) -> list[JsonValue]:
    if isinstance(current, dict):
        candidates = list(current.values())
    elif isinstance(current, list):
        candidates = list(current)
    else:
        return []
    if isinstance(step, Wild):
        return candidates
    chosen: list[JsonValue] = []
    for item in candidates:
        held = resolve_path(item, step.key)
        if held.found and scalar_equal(held.value, step.value):
            chosen.append(item)
    return chosen


def resolve_path(document: JsonValue, path: str) -> Resolved:
    """Walk `path` into `document`: whether it resolved, and to what."""
    current = document
    selection: list[JsonValue] | None = None
    for step in path_steps(path):
        if isinstance(step, Wild | Filter):
            if selection is None:
                selection = _selected(current, step)
            else:
                selection = [item for element in selection for item in _selected(element, step)]
            continue
        if selection is not None:
            selection = [hit.value for hit in (_step_into(element, step) for element in selection) if hit.found]
            continue
        hit = _step_into(current, step)
        if not hit.found:
            return Resolved(False)
        current = hit.value
    if selection is not None:
        return Resolved(bool(selection), selection)
    return Resolved(True, current)


def is_projection(path: str) -> bool:
    return any(isinstance(step, (Wild, Filter)) for step in path_steps(path))


def scalar_equal(observed: JsonValue, expected: JsonValue) -> bool:
    """`json_path(equals=)` against what the document holds, typed the way JSON types it."""
    if isinstance(expected, bool) or isinstance(observed, bool):
        return isinstance(observed, bool) and isinstance(expected, bool) and observed is expected
    if isinstance(expected, (int, float)):
        return isinstance(observed, (int, float)) and observed == expected
    if isinstance(expected, str):
        return isinstance(observed, str) and observed == expected
    return False
