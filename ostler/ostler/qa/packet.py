"""The `qa context` packet `compile-plan` reads, validated once into one typed record."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field
from typing import Any, cast

from ostler.data_states import DataState, Move
from ostler.passages import Passage
from ostler.qa.navigation import SurfaceNavigation
from ostler.qa.navigation import navigation_rows
from ostler.qa.obligation import Obligation
from ostler.qa.obligation import obligations_of


@dataclass(frozen=True)
class ContextPacket:
    """Everything `compile-plan` reads off one context packet: its claims and the book-wide tables beside them."""
    obligations: tuple[Obligation, ...]
    navigation: dict[str, SurfaceNavigation]
    screen_routes: dict[str, str]
    cli_binaries: dict[str, str]
    scenario_fixtures: frozenset[str]
    story_slug: str
    fragment_hosts: dict[str, str]
    browser_fixtures: frozenset[str] = frozenset()
    fixture_screens: dict[str, str] = field(default_factory=dict[str, str])
    server_origins: dict[str, str] = field(default_factory=dict[str, str])
    passages: dict[str, Passage] = field(default_factory=dict[str, Passage])
    data_states: dict[str, DataState] = field(default_factory=dict[str, DataState])
    moves: dict[str, tuple[Move, ...]] = field(default_factory=dict[str, tuple[Move, ...]])

    @property
    def owed(self) -> list[Obligation]:
        """The claims this change owes live evidence for."""
        return [o for o in self.obligations if o.required]

    @property
    def digest(self) -> str:
        """A digest of the owed obligation id set, which a compiled plan's `book=` names."""
        ids = sorted(o.id for o in self.owed if o.id)
        return hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()


def _string_table(value: object, what: str) -> dict[str, str]:
    """A packet mapping of string to string, empty when unset, refused loudly when anything else."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"context `{what}` is not a mapping: {value!r}")
    table: dict[str, str] = {}
    for key, item in value.items():
        if not (isinstance(key, str) and isinstance(item, str)):
            raise ValueError(f"context `{what}` maps {key!r} to {item!r}; both must be strings")
        table[key] = item
    return table


def _names(value: object, what: str) -> frozenset[str]:
    """A packet list of names, empty when unset, refused loudly when anything else."""
    if value is None:
        return frozenset()
    if not isinstance(value, list):
        raise ValueError(f"context `{what}` is not a list of strings: {value!r}")
    names: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"context `{what}` is not a list of strings: {value!r}")
        names.add(item)
    return frozenset(names)


def _passages(value: object) -> dict[str, Passage]:
    """The packet's passage table, empty when unset, refused loudly when a row is not a passage."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"context `passages` is not a mapping: {value!r}")
    table: dict[str, Passage] = {}
    for node, row in value.items():
        if not (isinstance(node, str) and isinstance(row, dict)):
            raise ValueError(f"context `passages` maps {node!r} to {row!r}; a passage is a mapping")
        start, end, steps, requests = row.get("from"), row.get("to"), row.get("steps"), row.get("requests", [])
        if not (isinstance(start, str) and isinstance(end, str)
                and isinstance(steps, list) and all(isinstance(step, str) for step in cast("list[object]", steps))
                and isinstance(requests, list) and all(isinstance(item, str) for item in cast("list[object]", requests))):
            raise ValueError(f"context `passages` row {node!r} needs `from`, `to`, `steps` and `requests` as strings: {row!r}")
        table[node] = Passage(node, start, tuple(cast("list[str]", steps)), end, tuple(cast("list[str]", requests)))
    return table


def _data_states(value: object) -> dict[str, DataState]:
    """The packet's data-state table, empty when unset, refused loudly when a row is not a data state."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"context `dataStates` is not a mapping: {value!r}")
    table: dict[str, DataState] = {}
    for node, row in value.items():
        if not (isinstance(node, str) and isinstance(row, dict)):
            raise ValueError(f"context `dataStates` maps {node!r} to {row!r}; a data state is a mapping")
        of, observe, method, path, verify = (row.get(key) for key in ("of", "observe", "method", "path", "verify"))
        if not (isinstance(of, str) and isinstance(observe, str) and isinstance(method, str) and isinstance(path, str)
                and isinstance(verify, list) and all(isinstance(item, str) for item in cast("list[object]", verify))):
            raise ValueError(
                f"context `dataStates` row {node!r} needs `of`, `observe`, `method`, `path` as strings and `verify` as a list: {row!r}")
        table[node] = DataState(node, of, observe, tuple(cast("list[str]", verify)), method, path)
    return table


def _moves(value: object) -> dict[str, tuple[Move, ...]]:
    """The packet's move table, empty when unset, refused loudly when a row is not a move."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"context `moves` is not a mapping: {value!r}")
    table: dict[str, tuple[Move, ...]] = {}
    for node, rows in value.items():
        if not (isinstance(node, str) and isinstance(rows, list)):
            raise ValueError(f"context `moves` maps {node!r} to {rows!r}; a node's moves are a list")
        moves: list[Move] = []
        for row in cast("list[object]", rows):
            start, end = (row.get("from"), row.get("to")) if isinstance(row, dict) else (None, None)
            if not (isinstance(start, str) and isinstance(end, str)):
                raise ValueError(f"context `moves` row {row!r} of {node!r} needs `from` and `to` as strings")
            moves.append(Move(start, end))
        table[node] = tuple(moves)
    return table


def packet_of(context: Mapping[str, Any]) -> ContextPacket:
    """*context* validated into a `ContextPacket`, refused loudly wherever it is malformed."""
    return ContextPacket(
        obligations=obligations_of(context.get("obligations")),
        navigation=navigation_rows(context.get("navigation")),
        screen_routes=_string_table(context.get("screenRoutes"), "screenRoutes"),
        cli_binaries=_string_table(context.get("cliBinaries"), "cliBinaries"),
        scenario_fixtures=_names(context.get("scenarioFixtures"), "scenarioFixtures"),
        story_slug=_string_table(context.get("story"), "story").get("slug", ""),
        fragment_hosts=_string_table(context.get("fragmentHosts"), "fragmentHosts"),
        browser_fixtures=_names(context.get("browserFixtures"), "browserFixtures"),
        fixture_screens=_string_table(context.get("fixtureScreens"), "fixtureScreens"),
        server_origins=_string_table(context.get("serverOrigins"), "serverOrigins"),
        passages=_passages(context.get("passages")),
        data_states=_data_states(context.get("dataStates")),
        moves=_moves(context.get("moves")),
    )
