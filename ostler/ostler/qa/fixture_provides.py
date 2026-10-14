"""The `node.key` facts each book fixture provides, through its own `provides:` and every fixture it `needs:`."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from ostler.qa.obligation_frame import BookNode


def closure(book: Mapping[str, BookNode]) -> dict[str, set[tuple[str, bool]]]:
    """`{fixture stem: {(`<owner>.<key>`, source-undetermined), ...}}` over the `needs:` closure."""
    fixtures = {node_id: node for node_id, node in book.items() if node.type == "fixture"}
    provides: dict[str, set[tuple[str, bool]]] = {}
    needs: dict[str, set[str]] = {}
    for node_id, node in fixtures.items():
        keys: set[tuple[str, bool]] = set()
        stated: dict[str, Mapping[str, str]] = {}
        for entry in node.entries.get("provides", ()):
            head = entry.headline.partition("—")[0].split()
            if head:
                stated[head[0]] = entry.properties
        for value in node.bullets.get("provides", ()):
            head = value.partition("—")[0].split()
            if not head:
                continue
            properties = stated.get(head[0], {})
            observed = bool(properties.get("from"))
            asserted = bool(properties.get("is"))
            keys.add((head[0], observed == asserted))
        provides[node_id] = keys
        needs[node_id] = {edge.to for edge in node.edges if edge.via == "needs" and edge.to in fixtures}

    resolved: dict[str, set[tuple[str, bool]]] = {}

    def resolve(node_id: str, seen: frozenset[str]) -> set[tuple[str, bool]]:
        if node_id in resolved:
            return resolved[node_id]
        if node_id in seen:
            return set()
        owner = Path(node_id).stem
        pairs = {(f"{owner}.{key}", bad) for key, bad in provides.get(node_id, ())}
        for dep in needs.get(node_id, ()):
            pairs |= resolve(dep, seen | {node_id})
        resolved[node_id] = pairs
        return pairs

    return {Path(node_id).stem: resolve(node_id, frozenset()) for node_id in fixtures}


def index(book: Mapping[str, BookNode]) -> dict[str, list[str]]:
    """Every book fixture's own `provides:` keys, plus every one reachable through `needs:`."""
    return {name: sorted(ref for ref, _ in pairs) for name, pairs in closure(book).items()}
