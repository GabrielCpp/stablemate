"""Each surface's navigation row from the context packet, read once into typed records."""

from __future__ import annotations

from dataclasses import dataclass

from ostler.qa.plan_source import ScenarioRefusal


@dataclass(frozen=True)
class NavHop:
    """One navigation edge on the route from a surface's start screen."""
    node: str
    from_page: str
    label: str


@dataclass(frozen=True)
class SurfaceNavigation:
    """One surface's navigation row: where its driver starts, and how it reaches each screen."""
    surface: str
    driver: str | None
    start: str
    entry_url: str | None
    root_path: str | None
    bundle_id: str | None
    launch_screen: str | None
    screen_count: int
    routes: dict[str, tuple[NavHop, ...]]
    unreachable: frozenset[str]
    undeclared: frozenset[str]
    opens: dict[str, str]

    def path_to(self, screen: str) -> str | None:
        """The path a walk to *screen* opens first: the entry its route starts from, else the surface's root."""
        return self.opens.get(screen, self.root_path)


def hops_from(hops: tuple[NavHop, ...], screen: str | None) -> tuple[NavHop, ...] | None:
    """The rest of *hops* from the last one that leaves *screen*, or None when the route never passes through it."""
    starts = [index for index, hop in enumerate(hops) if screen and hop.from_page == screen]
    return hops[starts[-1]:] if starts else None


@dataclass(frozen=True)
class MaestroLaunch:
    """How a mobile surface's app is launched, and the routes that reach past its first screen."""
    bundle_id: str
    launch_screen: str
    routes: dict[str, tuple[NavHop, ...]]


def _nav_hop(screen: str, hop: object) -> NavHop:
    """One route edge from the navigation packet, refused loudly when it is malformed."""
    fields = hop if isinstance(hop, dict) else {}
    node, from_page, label = fields.get("node"), fields.get("from"), fields.get("label")
    if not (isinstance(node, str) and isinstance(from_page, str) and isinstance(label, str)):
        raise ValueError(
            f"navigation route to {screen!r} carries a hop without a string `node`, `from` "
            f"and `label`: {hop!r}")
    return NavHop(node=node, from_page=from_page, label=label)


def _nav_hops(routes: object) -> dict[str, tuple[NavHop, ...]]:
    """The navigation packet's `routes`, one typed hop sequence per reachable screen."""
    if not isinstance(routes, dict):
        raise ValueError(f"navigation `routes` is not a mapping of screen to hops: {routes!r}")
    typed: dict[str, tuple[NavHop, ...]] = {}
    for screen, hops in routes.items():
        if not isinstance(hops, list):
            raise ValueError(f"navigation route to {screen!r} is not a list of hops: {hops!r}")
        typed[str(screen)] = tuple(_nav_hop(str(screen), hop) for hop in hops)
    return typed


def _optional_text(surface: str, key: str, value: object) -> str | None:
    """A packet string, `None` when the packet left it unset, refused loudly when it is anything else."""
    if value is None or isinstance(value, str):
        return value
    raise ValueError(f"navigation `{key}` for surface {surface!r} is not a string: {value!r}")


def _screen_count(surface: str, counts: object) -> int:
    """A navigation row's `counts.screens`, 0 when unset, refused loudly when not an int."""
    if counts is None:
        return 0
    if not isinstance(counts, dict):
        raise ValueError(f"navigation row for surface {surface!r} has `counts` that is not a mapping: {counts!r}")
    screens = counts.get("screens")
    if screens is None:
        return 0
    if isinstance(screens, bool) or not isinstance(screens, int):
        raise ValueError(f"navigation row for surface {surface!r} has `counts.screens` that is not an int: {screens!r}")
    return screens


def _screen_set(surface: str, key: str, value: object) -> frozenset[str]:
    """A packet list of screen ids as a set, empty when unset, refused loudly when malformed."""
    if value is None:
        return frozenset()
    if not isinstance(value, list) or not all(isinstance(screen, str) for screen in value):
        raise ValueError(
            f"navigation `{key}` for surface {surface!r} is not a list of screen ids: {value!r}")
    return frozenset(screen for screen in value if isinstance(screen, str))


def _screen_paths(surface: str, key: str, value: object) -> dict[str, str]:
    """A packet table of screen id to path, empty when unset, refused loudly when malformed."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"navigation `{key}` for surface {surface!r} is not a mapping of screen to path: {value!r}")
    paths: dict[str, str] = {}
    for screen, path in value.items():
        if not (isinstance(screen, str) and isinstance(path, str)):
            raise ValueError(f"navigation `{key}` for surface {surface!r} is not a mapping of screen to path: {value!r}")
        paths[screen] = path
    return paths


def surface_navigation(surface: str, row: object) -> SurfaceNavigation:
    """One surface's navigation row, refused loudly when it is not a mapping."""
    if not isinstance(row, dict):
        raise ValueError(f"navigation row for surface {surface!r} is not a mapping: {row!r}")
    return SurfaceNavigation(
        surface=surface,
        driver=_optional_text(surface, "driver", row.get("driver")),
        start=_optional_text(surface, "start", row.get("start")) or "",
        entry_url=_optional_text(surface, "entryUrl", row.get("entryUrl")),
        root_path=_optional_text(surface, "rootPath", row.get("rootPath")),
        bundle_id=_optional_text(surface, "bundleId", row.get("bundleId")),
        launch_screen=_optional_text(surface, "launchScreen", row.get("launchScreen")),
        screen_count=_screen_count(surface, row.get("counts")),
        routes=_nav_hops(row.get("routes") or {}),
        unreachable=_screen_set(surface, "unreachable", row.get("unreachable")),
        undeclared=_screen_set(surface, "undeclared", row.get("undeclared")),
        opens=_screen_paths(surface, "opens", row.get("opens")),
    )


def navigation_rows(packet: object) -> dict[str, SurfaceNavigation]:
    """Every surface's row of the packet's `navigation`, keyed by surface, refused loudly when malformed."""
    if packet is None:
        return {}
    if not isinstance(packet, dict):
        raise ValueError(f"context `navigation` is not a mapping of surface to row: {packet!r}")
    rows: dict[str, SurfaceNavigation] = {}
    for surface, row in packet.items():
        if not isinstance(surface, str):
            raise ValueError(f"context `navigation` names a non-string surface: {surface!r}")
        rows[surface] = surface_navigation(surface, row)
    return rows


def surface_row(navigation: dict[str, SurfaceNavigation], surface: str) -> SurfaceNavigation:
    """The row for *surface*, or an empty one when the packet names no such surface."""
    return navigation.get(surface) or surface_navigation(surface, {})


def entry_url_refusal(surface: str) -> ScenarioRefusal:
    """Why an obligation whose surface resolved to no address gets no scenario."""
    return ScenarioRefusal("undeclared-entry-url", (
        f"surface {surface!r} states no `entry-url:` on a `server` or `runbook` node, "
        "and no --base-url was passed to fall back on"
    ))


def maestro_launch(nav: SurfaceNavigation) -> MaestroLaunch | ScenarioRefusal:
    """The launch a Maestro flow on *nav*'s surface starts from, or why the book gives none."""
    if nav.bundle_id is None:
        return ScenarioRefusal("undeclared-bundle-id", (
            f"surface {nav.surface!r} states no `bundle-id:` on a `runbook` node"
        ))
    if nav.launch_screen is None:
        return ScenarioRefusal("undeclared-launch-screen", (
            f"surface {nav.surface!r} states no `launch-screen:` on a `runbook` node"
        ))
    routes = nav.routes if nav.start == nav.launch_screen else {}
    return MaestroLaunch(nav.bundle_id, nav.launch_screen, routes)
