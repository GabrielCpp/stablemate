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

    `iac`, `cli`, `artifact` and `none` own no node type this book's registry ever admits a
    `route:`/`path:` bullet on (`screen`, `endpoint`): an `iac` surface provisions
    infrastructure, a `cli` surface drives a command line, `artifact` addresses no node type
    this registry has, and `none` is the book stating outright that nothing performs against
    these surfaces at all — none of which is a screen a route addresses. So no corpus book
    today gives this predicate a value to read — it exists so `ROUTE_GRAMMAR`'s row for such a
    driver names a predicate and a reason like every other row, rather than leaving a hole a
    caller has to know to special-case. `doctor.py`'s `_check_bullet_value_kinds` calls
    `route_grammar` for every `route`/`path`-kinded bullet regardless of driver, so this
    predicate *is* on a real code path, not a hypothetical one — it would run the day a
    `screen`/`endpoint` node ends up on such a driven surface, however that came about, and it
    says no, honestly: a driver that states no routes cannot make an exception for one bullet
    that showed up anyway.
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
#: All seven §4.1 values get a row, covering four distinct situations —
#: `path_addressed=False` is not one story:
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
#: - `artifact` and `none` also read `is_never_routed` and are **not** path-addressed, each for
#:   its own reason rather than one shared with `iac`/`cli`'s node-type argument:
#:   - `none` is the book stating outright that nothing performs against these surfaces, so
#:     there is no driver whose addressing scheme a route could be held to — asking for a root
#:     path here asks for an address the book has said nothing navigates to.
#:   - `artifact` has no node type in this registry it could ever address at all —
#:     `SURFACE_PERFORMABLE_TYPES`'s own row for it is empty and settled, not merely
#:     unmeasured. A driver with nothing to address has no routes to grammar-check.
#:
#: A driver this table does not name at all — an unrecognized spelling, or no runbook declares
#: one — falls back to `(is_path_shaped, NOT_PATH_SHAPED_REASON, True)`, the one grammar this
#: module had before this table existed, so an undeclared surface's bullets are checked, and
#: treated as path-addressed, exactly as they always were. That fallback now narrows to its one
#: honest case: every §4.1 value has its own row above, so the default is reachable only by a
#: spelling *outside* §4.1's vocabulary entirely — a typo, or no driver declared — which has
#: stated nothing and keeps the benefit of the doubt.
ROUTE_GRAMMAR: dict[str, tuple[Callable[[str], bool], str, bool]] = {
    "web": (is_path_shaped, NOT_PATH_SHAPED_REASON, True),
    "http": (is_path_shaped, NOT_PATH_SHAPED_REASON, True),
    "mobile": (is_screen_name_shaped, NOT_SCREEN_NAME_SHAPED_REASON, False),
    "iac": (is_never_routed, NOT_ROUTED_REASON, False),
    "cli": (is_never_routed, NOT_ROUTED_REASON, False),
    "artifact": (is_never_routed, NOT_ROUTED_REASON, False),
    "none": (is_never_routed, NOT_ROUTED_REASON, False),
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
    paths) and `iac`/`cli`/`artifact`/`none` (no screen or endpoint at all, each for its own
    stated reason) are not — and asking any of them for a root *path* would be inventing an
    address the book has no grammar for.
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


#: Which surface node **types** a `driver:` (§4.1 of `docs/okf-runbook.md`) can actually
#: perform against, keyed the same way `ROUTE_GRAMMAR` is — one row per driver, stated
#: outright rather than inferred from that table. The two tables answer different questions
#: and must not be read off each other: `ROUTE_GRAMMAR` says whether a driver addresses a
#: screen/endpoint *by path*, a fact about navigation; this table says which node *type* a
#: driver is even capable of exercising, a fact about the surface. `iac` and `cli` share a row
#: in `ROUTE_GRAMMAR` (`is_never_routed`) because neither has a route grammar — but `cli`
#: performs against a very real `type: cli` node (the corpus's `tally-cli` app has one), while
#: `iac` provisions infrastructure no node type here represents at all. Route-less and
#: surface-less are independent properties; this table does not inherit the other's grouping.
#:
#: All seven driver values §4.1 names get a row, each reasoned on its own terms:
#:
#: - `web` -> `{"screen"}`, `mobile` -> `{"screen"}`: both drive a screen, one through a
#:   browser and one through a navigator; neither drives anything else this vocabulary types.
#: - `http` -> `{"server"}`: an HTTP driver issues requests at a `server` contract.
#: - `cli` -> `{"cli"}`: it drives a `type: cli` node — the dev-CLI a runbook's own `cli:`
#:   bullet also links, per `runbook.md`.
#: - `artifact` -> empty, and settled, not merely unmeasured: this registry has no `type:
#:   artifact` node at all (`registry.py`'s file-level UI types are `screen`, `cli`, `server`,
#:   `concept`, `format`, `flow`, `runbook`, `environment`, `fixture`) — there is no node this
#:   driver could ever be pointed at, the same gap `acts.py`'s `WEB`/`MOBILE`/`HTTP`/`CLI`
#:   table names for `artifact` on the arrangement side ("an arrangement it could make is an
#:   arrangement `fixture:` already covers").
#: - `iac` -> empty, but **measured, not reasoned**: the corpus's one `iac` runbook
#:   (`depot-infra`'s `preview-the-plan`) declares no `surfaces:` bullet at all, so there is
#:   nothing to generalize a row from. This is not a claim that infrastructure-as-code drives
#:   no surface type in general — an `iac` runbook that does declare `surfaces:` would settle
#:   it either way, and none exists yet.
#: - `none` -> empty, by construction: `driver: none` is the book stating outright that
#:   nothing performs against this runbook's surfaces, so there is no type such a driver could
#:   ever match — asking whether *some* surface matches a set that is empty by the driver's own
#:   declaration would be checking a claim the book never made.
#:
#: A driver this table does not name (an unrecognized spelling, or none declared) also reads as
#: empty via `performable_surface_types`'s default — unlike `ROUTE_GRAMMAR`'s fallback, which
#: extends its one general-purpose grammar to an unrecognized driver as the benefit of the
#: doubt. There is no such general-purpose *surface* grammar to fall back to here: an
#: unrecognized driver has stated nothing this table could hold it to, so `no-drivable-surface`
#: has nothing to check and skips it, the same as `iac`/`artifact`/`none`'s stated-empty rows —
#: for a different reason (nothing declared, vs. declared-and-empty) but the same shape of skip.
#:
#: `ROUTE_GRAMMAR` names `artifact` and `none` too, each with its own stated reason beside that
#: table — a driver with nothing to address, and a book declaring no performer at all, are
#: neither of them silently path-addressed any more.
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
    """The surface node types *driver* can perform against; empty when it performs against none.

    `SURFACE_PERFORMABLE_TYPES`'s row for a recognized driver — `artifact`/`iac`/`none`
    included, each stated empty for its own reason in the table's docstring, not a hole. An
    unrecognized driver (a typo, or none declared) also reads empty: unlike `route_grammar`,
    there is no general-purpose fallback grammar to extend to it, because this table states a
    capability rather than parsing a value every driver must produce something for.
    """
    return SURFACE_PERFORMABLE_TYPES.get(driver or "", frozenset())
