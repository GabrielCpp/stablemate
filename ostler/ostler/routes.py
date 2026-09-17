"""What a screen's `route:` bullet says about the address a browser would show.

Two readers ask this question and they must not answer it differently. A driver asks it of
a page it is looking at — is this the screen the book named? The plan compiler asks it of a
book it has not run — could that question be answered at all? A route that names a family of
pages makes the second answer no, and a compiler that decided that on its own regex would
drift away from the reader whose behaviour it is predicting.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from ostler.model import Graph


def literal_route(route: str) -> str:
    """The path a browser's URL must equal for this route, or "" when the route is a pattern.

    A route with a `{param}` in it names a family of pages, and no string comparison can say
    whether the one on screen is a member. Rather than match loosely — which would let a vet
    establish the wrong subject and report every verdict about it anyway — a pattern route
    returns nothing and the caller says it could not establish the screen.
    """
    text = route.strip()
    if not text.startswith("/") or "{" in text or "*" in text:
        return ""
    # `/links/:id/edit` is the other pattern spelling this book uses — see `entry:` on the
    # screen page. Compared as a literal it can never equal a real URL, so every vet of a
    # parameterised screen would stop its scenario for not arriving where it plainly did.
    if any(segment.startswith(":") for segment in text.split("/")):
        return ""
    return text.rstrip("/") or "/"


def arrived_at(url: str, route: str) -> bool:
    """Whether a page at *url* is the screen documented at *route*.

    Compares paths only: a query string and a fragment are state within a screen, not a
    different screen, and a book that had to enumerate them could never be written.
    """
    path = urlsplit(url).path
    return (path.rstrip("/") or "/") == literal_route(route)


def screen_routes(graph: Graph) -> dict[str, str]:
    """Each documented screen's `route:`, keyed the way `screen_components` keys components.

    The route is what a reader of a rendered page has to go on to say *which* screen it is:
    a screen node carries no other bullet that a browser could be asked about. A file
    documenting two screens is left out rather than guessed at — two routes and one page is
    an ambiguity, and a vet that picked one of them would establish its subject by coin-toss.
    """
    routes: dict[str, set[str]] = {}
    for node in graph.ui_nodes:
        if node.type != "screen":
            continue
        route = str(node.meta.get("route", "")).strip().strip("`").strip()
        if route:
            routes.setdefault(node.id.split("#")[0], set()).add(route)
    return {path: next(iter(found)) for path, found in routes.items() if len(found) == 1}
