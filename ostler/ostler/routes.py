"""What a screen's `route:` bullet says about the address a browser would show."""

from __future__ import annotations

import re

from collections.abc import Callable, Iterable
from urllib.parse import urlsplit

from ostler.model import Graph, fragment_host


def is_path_shaped(route: str) -> bool:
    """Whether *route* could be a path at all — the question a browser could even be asked. A path begins with `/` and holds no whitespace."""
    text = route.strip()
    return text.startswith("/") and not any(character.isspace() for character in text)


NOT_PATH_SHAPED_REASON = "it is not a path (a path begins with `/` and holds no whitespace)"


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
    if not text.startswith("/") or "{" in text or "*" in text or "?" in text:
        return ""
    if any(segment.startswith(":") for segment in text.split("/")):
        return ""
    return text.rstrip("/") or "/"


_QUERY_MARK = re.compile(r"\?(?=[^/])")


def entry_address(entry: str) -> str:
    """The address a browser opens for an `entry:`: its literal path with any query string it states, or "" when the path is a pattern. A `?` that ends a segment marks it optional, and any other `?` starts a query."""
    text = entry.strip()
    query = _QUERY_MARK.search(text)
    path, rest = (text[:query.start()], text[query.start():]) if query else (text, "")
    literal = literal_route(path)
    return literal + rest if literal else ""


def route_pattern(route: str) -> re.Pattern[str] | None:
    """The pattern a browser's path must match for this route, or None when no URL comparison can use it. A `:name` or `{name}` segment stands for exactly one path segment, and a segment ending in `?` may be absent."""
    text = route.strip()
    if not is_path_shaped(text) or "*" in text:
        return None
    parts: list[str] = []
    for raw in text.strip("/").split("/"):
        optional = raw.endswith("?")
        segment = raw.removesuffix("?")
        if segment.startswith(":") or (segment.startswith("{") and segment.endswith("}")):
            part = "/[^/]+"
        elif "{" in segment or "}" in segment or "?" in segment:
            return None
        elif segment:
            part = "/" + re.escape(segment)
        else:
            continue
        parts.append(f"(?:{part})?" if optional else part)
    return re.compile("".join(parts) or "/")


def is_comparable(route: str) -> bool:
    """Whether a page's URL can be held against *route* at all."""
    return route_pattern(route) is not None


def arrival_regex(route: str, others: Iterable[str] = ()) -> str:
    """A regex a whole URL fullmatches when the page it names is the screen at *route*, or "" when no URL comparison can say. A parameterised route loses to any of *others* that spells the same path literally."""
    pattern = route_pattern(route)
    if pattern is None:
        return ""
    taken = sorted({
        literal for other in others
        if (literal := literal_route(other)) and literal != literal_route(route) and pattern.fullmatch(literal)})
    refused = "".join(rf"(?!{re.escape(path)}/?(?:[?#].*)?$)" for path in taken)
    return rf"[^/]+//[^/]+{refused}{pattern.pattern}/?(?:[?#].*)?"


def why_unreadable(route: str) -> str:
    """Why `route_pattern` returned nothing for *route*, in the book's own terms."""
    text = route.strip()
    if not text:
        return "the book states no single `route:` for it"
    if is_comparable(text):
        return ""
    if not is_path_shaped(text):
        return f"its `route:` (`{_excerpt(text)}`) is not a path a browser could show"
    return f"its `route:` (`{_excerpt(text)}`) names a family of pages"


def _excerpt(text: str) -> str:
    """*text* on one line, short enough to read inside a finding."""
    one_line = " ".join(text.split())
    return one_line if len(one_line) <= 60 else one_line[:57] + "..."


def arrived_at(url: str, route: str, others: Iterable[str] = ()) -> bool:
    """Whether a page at *url* is the screen documented at *route*. A parameterised route loses to any of *others* that spells the same path literally."""
    path = urlsplit(url).path.rstrip("/") or "/"
    literal = literal_route(route)
    if literal:
        return path == literal
    pattern = route_pattern(route)
    if pattern is None or pattern.fullmatch(path) is None:
        return False
    return all(literal_route(other) != path for other in others)


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


def vet_routes(graph: Graph) -> dict[str, str]:
    """`screen_routes`, plus each fragment page under the route of the screen its `host:` chain ends on."""
    routes = screen_routes(graph)
    hosts = {node.id: fragment_host(node, graph.root) for node in graph.ui_nodes
             if node.type == "fragment" and node.kind == "file"}
    for fragment in hosts:
        page, seen = fragment, {fragment}
        while page not in routes and hosts.get(page, "") not in seen | {""}:
            page = hosts[page]
            seen.add(page)
        if page in routes:
            routes[fragment] = routes[page]
    return routes


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
