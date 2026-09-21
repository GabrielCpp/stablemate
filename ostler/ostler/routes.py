"""What a screen's `route:` bullet says about the address a browser would show."""

from __future__ import annotations

import re

from collections.abc import Callable
from urllib.parse import urlsplit

from ostler.model import Graph


def is_path_shaped(route: str) -> bool:
    """Whether *route* could be a path at all — the question a browser could even be asked."""
    return route.strip().startswith("/")


NOT_PATH_SHAPED_REASON = "it is not a path (it does not begin with `/`)"


def is_screen_name_shaped(route: str) -> bool:
    """Whether *route* could be a React Navigation screen name — the mobile counterpart of `is_path_shaped`."""
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", route.strip()))


NOT_SCREEN_NAME_SHAPED_REASON = (
    "it is not a navigator screen name (an identifier, not a path or a URL)"
)


def is_never_routed(route: str) -> bool:
    """Always false — the predicate for a driver that states no routes at all."""
    del route
    return False


NOT_ROUTED_REASON = "this driver states no routes at all — it owns no screen or endpoint node"


ROUTE_GRAMMAR: dict[str, tuple[Callable[[str], bool], str, bool]] = {
    "web": (is_path_shaped, NOT_PATH_SHAPED_REASON, True),
    "http": (is_path_shaped, NOT_PATH_SHAPED_REASON, True),
    "mobile": (is_screen_name_shaped, NOT_SCREEN_NAME_SHAPED_REASON, False),
    "iac": (is_never_routed, NOT_ROUTED_REASON, False),
    "cli": (is_never_routed, NOT_ROUTED_REASON, False),
    "artifact": (is_never_routed, NOT_ROUTED_REASON, False),
    "none": (is_never_routed, NOT_ROUTED_REASON, False),
}

_DEFAULT_ROUTE_GRAMMAR: tuple[Callable[[str], bool], str, bool] = (
    is_path_shaped, NOT_PATH_SHAPED_REASON, True,
)


def route_grammar(driver: str | None) -> tuple[Callable[[str], bool], str]:
    """The `(predicate, reason)` pair *driver* is held to."""
    predicate, reason, _path_addressed = ROUTE_GRAMMAR.get(driver or "", _DEFAULT_ROUTE_GRAMMAR)
    return predicate, reason


def is_path_addressed(driver: str | None) -> bool:
    """Whether *driver* names its screens by a path at all."""
    _predicate, _reason, path_addressed = ROUTE_GRAMMAR.get(driver or "", _DEFAULT_ROUTE_GRAMMAR)
    return path_addressed


def literal_route(route: str) -> str:
    """The path a browser's URL must equal for this route, or "" when the route is a pattern."""
    text = route.strip()
    if not text.startswith("/") or "{" in text or "*" in text:
        return ""
    if any(segment.startswith(":") for segment in text.split("/")):
        return ""
    return text.rstrip("/") or "/"


def why_unreadable(route: str) -> str:
    """Why `literal_route` returned nothing for *route*, in the book's own terms."""
    text = route.strip()
    if not text:
        return "the book states no single `route:` for it"
    if literal_route(text):
        return ""
    if not is_path_shaped(text):
        return f"its `route:` (`{_excerpt(text)}`) is not a path a browser could show"
    return f"its `route:` (`{_excerpt(text)}`) names a family of pages"


def _excerpt(text: str) -> str:
    """*text* on one line, short enough to read inside a finding."""
    one_line = " ".join(text.split())
    return one_line if len(one_line) <= 60 else one_line[:57] + "..."


def arrived_at(url: str, route: str) -> bool:
    """Whether a page at *url* is the screen documented at *route*."""
    path = urlsplit(url).path
    return (path.rstrip("/") or "/") == literal_route(route)


def screen_routes(graph: Graph) -> dict[str, str]:
    """Each documented screen's `route:`, keyed the way `screen_components` keys components."""
    routes: dict[str, set[str]] = {}
    for node in graph.ui_nodes:
        if node.type != "screen":
            continue
        route = str(node.meta.get("route", "")).strip().strip("`").strip()
        if route:
            routes.setdefault(node.id.split("#")[0], set()).add(route)
    return {path: next(iter(found)) for path, found in routes.items() if len(found) == 1}


SURFACE_PERFORMABLE_TYPES: dict[str, frozenset[str]] = {
    "web": frozenset({"screen"}),
    "mobile": frozenset({"screen"}),
    "http": frozenset({"server"}),
    "cli": frozenset({"cli"}),
    "artifact": frozenset(),
    "iac": frozenset(),
    "none": frozenset(),
}


def performable_surface_types(driver: str | None) -> frozenset[str]:
    """The surface node types *driver* can perform against; empty when it performs against none."""
    return SURFACE_PERFORMABLE_TYPES.get(driver or "", frozenset())
