"""What a screen's `route:` bullet says about the address a browser would show.

Two readers ask this question and they must not answer it differently. A driver asks it of
a page it is looking at — is this the screen the book named? The plan compiler asks it of a
book it has not run — could that question be answered at all? A route that names a family of
pages makes the second answer no, and a compiler that decided that on its own regex would
drift away from the reader whose behaviour it is predicting.
"""

from __future__ import annotations

import re

from collections.abc import Callable
from urllib.parse import urlsplit

from ostler.model import Graph


def is_path_shaped(route: str) -> bool:
    """Whether *route* could be a path at all — the question a browser could even be asked.

    This is the line `why_unreadable` draws between its two negative reasons: a value that
    fails this is not a path (a framework's route *name*, a sentence, a bare identifier), while
    a value that passes it but still fails `literal_route` is a path that names a *family* of
    pages (a `{param}` or `:id` segment) — a different defect with a different repair. Callers
    that only need the first question, not which path, use this rather than re-testing the
    leading `/` themselves.
    """
    return route.strip().startswith("/")


#: Why `is_path_shaped` said no, as a statement about the *value* — kept beside the predicate it
#: describes, and naming no bullet. `why_unreadable` answers for a `route:` specifically and says
#: so in its own words; a caller checking some other key (`endpoint.path`) names its own key and
#: needs only this half, which is why the reason here mentions none.
NOT_PATH_SHAPED_REASON = "it is not a path (it does not begin with `/`)"


def is_screen_name_shaped(route: str) -> bool:
    """Whether *route* could be a React Navigation screen name — the mobile counterpart of
    `is_path_shaped`.

    A `Stack.Screen name="WidgetList"` value is the identifier a navigator that routes on
    names keys its screens by, not an address a browser would show: no leading `/`, no
    scheme, no host — the bare identifier the navigator's own `name` prop already is. A
    mobile screen's `route:` states this, never a path, because a navigator that routes on
    names has no path to state.
    """
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", route.strip()))


#: Why `is_screen_name_shaped` said no — kept beside the predicate for the same reason
#: `NOT_PATH_SHAPED_REASON` is kept beside `is_path_shaped`.
NOT_SCREEN_NAME_SHAPED_REASON = (
    "it is not a navigator screen name (an identifier, not a path or a URL)"
)


def is_never_routed(route: str) -> bool:
    """Always false — the predicate for a driver that states no routes at all.

    `iac` and `cli` own no node type this book's registry ever admits a `route:`/`path:`
    bullet on (`screen`, `endpoint`): an `iac` surface provisions infrastructure and a `cli`
    surface drives a command line, neither of which is a screen a route addresses. So no
    corpus book today gives this predicate a value to read — it exists so `ROUTE_GRAMMAR`'s
    row for such a driver names a predicate and a reason like every other row, rather than
    leaving a hole a caller has to know to special-case. `doctor.py`'s
    `_check_bullet_value_kinds` calls `route_grammar` for every `route`/`path`-kinded bullet
    regardless of driver, so this predicate *is* on a real code path, not a hypothetical one
    — it would run the day a `screen`/`endpoint` node ends up on an `iac`- or `cli`-driven
    surface, however that came about, and it says no, honestly: a driver that states no
    routes cannot make an exception for one bullet that showed up anyway.
    """
    del route
    return False


#: Why `is_never_routed` said no — kept beside the predicate for the same reason the other two
#: reasons are kept beside theirs. Distinct from `NOT_PATH_SHAPED_REASON` and
#: `NOT_SCREEN_NAME_SHAPED_REASON`: those describe a bullet that failed a real grammar, this one
#: describes a driver that has no grammar for a bullet to fail.
NOT_ROUTED_REASON = "this driver states no routes at all — it owns no screen or endpoint node"


#: Which grammar a `route:`/`path:` bullet is held to, keyed by the surface's declared
#: `driver:` (`reach.surface_driver`) — one parser per driver, never a grammar invented for
#: this table, per `values.py`'s rule that a declared kind names the parser its consumer
#: already uses. Each row is `(predicate, reason, path_addressed)`: `path_addressed` is a
#: **stated** property of the driver, not inferred from which predicate the row happens to
#: hold — two drivers could share a predicate (a stricter path grammar reused by both `web`
#: and a future driver) without either becoming the other's synonym for "addresses by path".
#: Reading it off predicate identity instead (`predicate is is_path_shaped`) would make the
#: day a path-addressed driver needs a different predicate silently stop being path-addressed
#: — and the consequence of that is not a wrong message, it is `_check_reachability` skipping
#: the whole surface's reachability check. That failure mode is exactly why this is its own
#: column: adding a row forces the author to answer "does this driver address by path?" on
#: purpose, rather than inherit an answer from which function object they reused.
#:
#: Four rows, three distinct situations — `path_addressed=False` is not one story:
#:
#: - `web` and `http` share this module's own grammar (`is_path_shaped`) and are path-addressed:
#:   a browser's URL and an HTTP endpoint's path are the same kind of address, whichever of the
#:   two drives it.
#: - `mobile` reads `is_screen_name_shaped` instead and is **not** path-addressed — a React
#:   Navigation `Stack.Screen name=` value, the only address a driver that routes on names has
#:   to state. No driver in this tree compiles a mobile scenario yet (`qa/compile.py`'s
#:   `_BUILT_TARGETS`), so today this row is read by `doctor.py` alone, ahead of the driver
#:   that will read it the same way.
#: - `iac` and `cli` read `is_never_routed` and are **not** path-addressed either, but for a
#:   different reason than `mobile`: `mobile` addresses its screens, just not by path; `iac` and
#:   `cli` address no screen or endpoint at all, because neither node type is ever owned by such
#:   a surface — there is no route for this table to grammar-check, and the row says so rather
#:   than falling through to the default as if the driver were merely unrecognized. `cli` reuses
#:   a word `tally-cli` (the corpus's one `cli`-shaped app) already spends on a *node* type
#:   (`type: cli`) — deliberate, the same way `web` already names both a driver and the family of
#:   nodes it drives, not a collision to "fix". No runbook in the corpus declares `driver: cli`
#:   yet (seven declare a driver today, `tally-cli` is not one of them); this table only adds the
#:   vocabulary a future one can use.
#:
#: A driver this table does not name at all — unrecognized, or no runbook declares one —
#: falls back to `(is_path_shaped, NOT_PATH_SHAPED_REASON, True)`, the one grammar this module
#: had before this table existed, so an undeclared surface's bullets are checked, and treated as
#: path-addressed, exactly as they always were. That fallback is a fourth, deliberately
#: different case from `iac`/`cli`: those two are *recognized* and *state* they have no routes;
#: an undeclared driver has stated nothing at all, and keeps the benefit of the doubt.
ROUTE_GRAMMAR: dict[str, tuple[Callable[[str], bool], str, bool]] = {
    "web": (is_path_shaped, NOT_PATH_SHAPED_REASON, True),
    "http": (is_path_shaped, NOT_PATH_SHAPED_REASON, True),
    "mobile": (is_screen_name_shaped, NOT_SCREEN_NAME_SHAPED_REASON, False),
    "iac": (is_never_routed, NOT_ROUTED_REASON, False),
    "cli": (is_never_routed, NOT_ROUTED_REASON, False),
}

#: The fallback row for a driver `ROUTE_GRAMMAR` does not name — see the table's own docstring.
_DEFAULT_ROUTE_GRAMMAR: tuple[Callable[[str], bool], str, bool] = (
    is_path_shaped, NOT_PATH_SHAPED_REASON, True,
)


def route_grammar(driver: str | None) -> tuple[Callable[[str], bool], str]:
    """The `(predicate, reason)` pair *driver* is held to.

    `ROUTE_GRAMMAR`'s row for a recognized driver (`iac`/`cli` included — their row is
    `is_never_routed`, not a hole); the default `is_path_shaped` grammar for a driver the table
    does not name at all (an unrecognized value, or none declared).

    This is the table's only production reader for the predicate/reason half:
    `doctor.py`'s `_check_bullet_value_kinds` calls it, per node, for whatever driver
    `reach.surface_driver` resolves the node's surface to, and applies the pair directly —
    there is no second, hand-written branch anywhere that repeats what a row says. Adding a
    row here is therefore sufficient on its own to change what that check accepts; nothing
    else needs to be told. `is_path_addressed`, below, is the table's other reader, for the
    third column alone.
    """
    predicate, reason, _path_addressed = ROUTE_GRAMMAR.get(driver or "", _DEFAULT_ROUTE_GRAMMAR)
    return predicate, reason


def is_path_addressed(driver: str | None) -> bool:
    """Whether *driver* names its screens by a path at all.

    `reach.root_path` and the `no-root-screen` check both speak of "the root path" — a
    question that presupposes a path grammar. Reads `ROUTE_GRAMMAR`'s own stated
    `path_addressed` column, not which predicate a row happens to hold — two drivers can
    share a predicate without sharing this answer, so the table says it outright instead of
    letting a caller infer it. `web`/`http`, and any driver this table does not recognize (an
    undeclared driver keeps today's grammar), are path-addressed; `mobile` (screen names, not
    paths) and `iac`/`cli` (no screen or endpoint at all) are not, each for its own stated
    reason — and asking any of the three for a root *path* would be inventing an address the
    book has no grammar for.
    """
    _predicate, _reason, path_addressed = ROUTE_GRAMMAR.get(driver or "", _DEFAULT_ROUTE_GRAMMAR)
    return path_addressed


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


def why_unreadable(route: str) -> str:
    """Why `literal_route` returned nothing for *route*, in the book's own terms.

    The reading and the reason for it belong to the same module: a caller that reported "names
    a family of pages" for every empty answer would be describing one of three different books
    — a parameterised path, a bullet that is not a path at all (a framework's route *name*, a
    sentence, a prose "none"), and a file that states no route or two — and each has a
    different repair. A message that names the wrong one sends the author to fix a thing that
    is not wrong.

    Returns "" when the route *is* readable, so a caller can use it as the condition.
    """
    text = route.strip()
    if not text:
        return "the book states no single `route:` for it"
    if literal_route(text):
        return ""
    if not is_path_shaped(text):
        # The real books reached for by reverse-engineering write the framework's route *name*
        # here, sometimes with the path in a parenthetical after it. That is a fact about the
        # source, not an address, and a browser cannot be asked about it.
        return f"its `route:` (`{_excerpt(text)}`) is not a path a browser could show"
    return f"its `route:` (`{_excerpt(text)}`) names a family of pages"


def _excerpt(text: str) -> str:
    """*text* on one line, short enough to read inside a finding."""
    one_line = " ".join(text.split())
    return one_line if len(one_line) <= 60 else one_line[:57] + "..."


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
