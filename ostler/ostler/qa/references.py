"""The one reference grammar `fixture:`/`needs:`/route paths/request bodies/`verify:` share."""

from __future__ import annotations

import re
from dataclasses import dataclass

_NODE_REF = re.compile(r"(?<![\w.])@([a-zA-Z0-9][a-zA-Z0-9_-]*)\.([a-zA-Z0-9][a-zA-Z0-9_-]*)")
_CAPTURE_REF = re.compile(r"(?<![\w.])\$([a-zA-Z0-9][a-zA-Z0-9_-]*)")


@dataclass(frozen=True)
class NodeRef:
    """`@node.key` — a fact a fixture node's own `provides:` declares."""
    node: str
    key: str


@dataclass(frozen=True)
class CaptureRef:
    """`$name` — a fact some earlier `capture:` bullet in the scenario left behind."""
    name: str


Reference = NodeRef | CaptureRef


def find_references(text: str) -> list[Reference]:
    """Every `@node.key` and `$name` reference embedded in *text*, in order of appearance."""
    refs: list[tuple[int, Reference]] = []
    for match in _NODE_REF.finditer(text):
        refs.append((match.start(), NodeRef(match.group(1), match.group(2))))
    for match in _CAPTURE_REF.finditer(text):
        refs.append((match.start(), CaptureRef(match.group(1))))
    refs.sort(key=lambda pair: pair[0])
    return [ref for _pos, ref in refs]


def parse_reference(value: str) -> Reference | None:
    """A bare `@node.key` or `$name` value, whole-string — the shape `fixture:`/`needs:` use."""
    stripped = value.strip()
    matched = _NODE_REF.fullmatch(stripped)
    if matched:
        return NodeRef(matched.group(1), matched.group(2))
    matched = _CAPTURE_REF.fullmatch(stripped)
    if matched:
        return CaptureRef(matched.group(1))
    return None
