"""The data an app's own server hands a page, for an app that renders some of a page's lists on its server. A SvelteKit
server answers `<path>/__data.json` with the data its loads returned for that page, serialized with devalue. This
module names that feed and decodes the answer into the value the page's `data` prop sees."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any

from ostler.book.errors import BookError

SPARSE = -7
SPECIALS = {-1: None, -3: math.nan, -4: math.inf, -5: -math.inf, -6: -0.0}
HOLE = -2
PARAM = re.compile(r"\[[^\]]+\]")


@dataclass(frozen=True)
class Handed:
    """The data the app's server hands the page of `route`, written as SvelteKit spells a route (`/tickets/[id]`)."""

    route: str

    @property
    def text(self) -> str:
        return f"data handed with the page of {self.route}"


def handed(route: str) -> Handed:
    return Handed(route)


def pattern(route: str) -> re.Pattern[str]:
    """The regular expression a path must match to be a page of `route`. Route groups are not in the path."""
    parts = [part for part in route.split("/") if part and not (part.startswith("(") and part.endswith(")"))]
    out = ""
    for part in parts:
        if part.startswith("[[") and part.endswith("]]"):
            out += "(?:/[^/]+)?"
        elif part.startswith("[...") and part.endswith("]"):
            out += "(?:/.+)?"
        elif PARAM.fullmatch(part):
            out += "/[^/]+"
        else:
            out += "/" + re.escape(part)
    return re.compile(out or "/")


def on_route(route: str, path: str) -> bool:
    """Whether `path` is a page of `route`."""
    return pattern(route).fullmatch(path.rstrip("/") or "/") is not None


class Hydrator:
    def __init__(self, values: list[Any]):
        self.values = values
        self.done: dict[int, Any] = {}

    def at(self, index: int) -> Any:
        if index in SPECIALS:
            return SPECIALS[index]
        if index == HOLE:
            return None
        if not isinstance(index, int) or isinstance(index, bool) or index < 0 or index >= len(self.values):
            raise BookError(f"the data handed with the page points at {index!r}, which it does not hold")
        if index in self.done:
            return self.done[index]
        value = self.values[index]
        if isinstance(value, list):
            return self.array(index, value)
        if isinstance(value, dict):
            made: dict[str, Any] = {}
            self.done[index] = made
            for key, item in value.items():
                made[key] = self.at(item)
            return made
        self.done[index] = value
        return value

    def array(self, index: int, value: list[Any]) -> Any:
        if value and isinstance(value[0], str):
            return self.typed(index, value)
        if value and value[0] == SPARSE:
            made: list[Any] = [None] * value[1]
            self.done[index] = made
            for at in range(2, len(value), 2):
                made[value[at]] = self.at(value[at + 1])
            return made
        items: list[Any] = []
        self.done[index] = items
        for item in value:
            items.append(self.at(item))
        return items

    def typed(self, index: int, value: list[Any]) -> Any:
        kind = value[0]
        if kind == "Date":
            self.done[index] = value[1]
        elif kind == "Set":
            found: list[Any] = []
            self.done[index] = found
            found.extend(self.at(item) for item in value[1:])
        elif kind == "Map":
            mapped: dict[Any, Any] = {}
            self.done[index] = mapped
            for at in range(1, len(value), 2):
                key = self.at(value[at])
                try:
                    mapped[key] = self.at(value[at + 1])
                except TypeError:
                    raise BookError(f"the data handed with the page has a map keyed by {key!r}, which cannot be a key") from None
        elif kind == "BigInt":
            self.done[index] = int(value[1])
        elif kind == "RegExp":
            self.done[index] = value[1]
        elif kind == "null":
            bare: dict[str, Any] = {}
            self.done[index] = bare
            for at in range(1, len(value), 2):
                bare[value[at]] = self.at(value[at + 1])
        elif kind == "Object":
            self.done[index] = self.at(value[1])
        else:
            raise BookError(f"the data handed with the page holds a {kind}, which a book cannot read")
        return self.done[index]


def unflatten(flat: Any) -> Any:
    """The value a devalue-flattened array stands for. Index 0 is the root."""
    if not isinstance(flat, list) or not flat:
        raise BookError("the data handed with the page is not a devalue array")
    return Hydrator(flat).at(0)


def decode(body: str | bytes) -> dict[str, Any]:
    """The page's data from the body of a `__data.json` answer: the data nodes, layouts first, merged into one
    dictionary with the page last. A skipped node adds nothing."""
    text = body.decode() if isinstance(body, bytes) else body
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) != 1:
        raise BookError(f"the app's server streamed its data in {len(lines)} lines, and a book reads one")
    try:
        answer = json.loads(lines[0])
    except ValueError as bad:
        raise BookError(f"the app's server answered something that is not JSON: {bad}") from None
    kind = answer.get("type") if isinstance(answer, dict) else None
    if kind == "redirect":
        raise BookError(f"the app's server redirected to {answer.get('location')!r} instead of handing data")
    if kind != "data":
        raise BookError(f"the app's server answered a {kind!r} where it hands data: {lines[0][:200]}")
    merged: dict[str, Any] = {}
    for node in answer.get("nodes", []):
        if node is None or node.get("type") == "skip":
            continue
        if node.get("type") == "error":
            raise BookError(f"a load of the page failed: {json.dumps(node.get('error'))}")
        if node.get("type") != "data":
            raise BookError(f"a node of the page's data is a {node.get('type')!r}, which a book cannot read")
        data = unflatten(node["data"])
        if not isinstance(data, dict):
            raise BookError("a load of the page returned something that is not an object")
        merged.update(data)
    return merged
