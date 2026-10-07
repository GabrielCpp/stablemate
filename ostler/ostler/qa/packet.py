"""The `qa context` packet `compile-plan` reads, validated once into one typed record."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field
from typing import Any

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
    )
