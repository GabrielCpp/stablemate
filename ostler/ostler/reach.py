"""``ostler reach`` — derive how to navigate to a screen, from the book alone.

The OKF records how screens are wired together: a component's ``leads-to:`` bullet says
*activating this takes you there*, and a flow's ``steps:`` are an ordered walk whose consecutive
entries land on different screens. Both are already in the graph; what was missing is reading them
as a route rather than as prose.

That is the point of the profile. A screen with no derivable route is not a screen you should
reach by typing its URL — it is a hole in the book, because a real user could not have gotten
there either. So an unreachable target is a finding, and this module reports it as one rather
than falling back to the ``route:`` bullet.

A route is a click-path *plus* what the caller must already satisfy to walk it. Screens declare
that in two required bullets: ``requires:`` (guard components that redirect when unmet) and
``params:`` (route parameters naming the interaction that mints the entity). Both are required
even when empty, so ``none`` is a statement and a missing bullet is a defect — a walk cannot
distinguish "nothing to satisfy" from "nobody wrote it down".
"""

from __future__ import annotations

import re

from collections import deque
from urllib.parse import urlparse

from ostler import graph as graph_mod, markdown, routes as routes_mod
from ostler.model import Graph
from ostler.qa.runbook import bullet_value

# The one bullet that means "activating this moves the user to that screen". `extends:`/`parent:`
# are structure and `on:` is attachment; none of them are things a user can do.
NAV_BULLET = "leads-to"
STEP_BULLET = "steps"
GUARD_BULLET = "requires"
PARAM_BULLET = "params"
# A screen entered from outside in-app navigation — an emailed deep link, an OAuth callback. Its
# value says *how*, and only a value that *is* a route (a path or an absolute URL) seeds the
# traversal: a walk can open `/reset/:token`, and cannot open "reached by typing the URL". Prose
# is a description, not a door; the screen it sits on still has to be reachable by clicking.
ENTRY_BULLET = "entry"
ROUTE_BULLET = "route"
# The surface's root is the screen whose `route:` is the path of its server's `entry-url:` —
# the address the walk actually opens — or `/` when no server contract states one. Every other
# screen is reached from it, or from a route-valued `entry:`.
ROOT_PATH = "/"
SERVER_TYPE = "server"
ENTRY_URL_BULLET = "entry-url"
WALKTHROUGH_BULLET = "walkthrough"
# The literal that means "declared, and empty". Anything else is a real precondition.
NONE = "none"
# The spellings authors actually use for it. Recognizing only the canonical one is not the strict
# reading it looks like — it is a silent wrong answer: `name: n/a` would be read as an accessible
# name, and the derived locator would hunt for a control literally called "n/a", failing at runtime
# as though the app were at fault. A sentinel the tooling does not know is worse than no sentinel.
NONE_TOKENS = frozenset({NONE, "n/a", "n.a.", "na", "-", "—", "–", ""})


def _values(value: object) -> list[str]:
    """A bullet's values as a flat list — scalar or nested, the caller does not care which."""
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)] if str(value).strip() else []


def _is_none(raw: str) -> bool:
    """Whether a precondition value states "nothing to satisfy".

    Authors rarely write a bare ``none`` — they write ``none — public route, no auth guard``,
    because the *reason* is the useful part. Matching only the bare token would read that as a
    guard literally named "none — public route…", inventing a precondition out of an explanation.
    """
    head = re.split(r"[—:(]", raw.strip(), maxsplit=1)[0]
    return head.strip().lower() in NONE_TOKENS


def preconditions(node: dict) -> dict:
    """What a caller must satisfy before this screen can render.

    ``declared`` is the honest bit: False means the bullets are missing, which is *not* the same
    as unconditional. Callers must treat an undeclared screen as unverifiable rather than free.
    """
    meta = node.get("bullets", {})
    guards, params = [], []
    for raw in _values(meta.get(GUARD_BULLET, "")):
        if _is_none(raw):
            continue
        links = markdown.extract_refs(raw).links
        guards.append({"text": raw.strip(), "node": links[0][1] if links else ""})
    for raw in _values(meta.get(PARAM_BULLET, "")):
        if _is_none(raw):
            continue
        idx = markdown.label_colon_index(raw)
        name, source = (raw[:idx], raw[idx + 1:]) if idx != -1 else (raw, "")
        links = markdown.extract_refs(source).links
        params.append({"name": name.strip(), "text": source.strip(),
                       "from": links[0][1] if links else ""})
    return {
        "declared": GUARD_BULLET in meta and PARAM_BULLET in meta,
        "guards": guards,
        "params": params,
    }


def _screen_of(node_id: str, by_id: dict) -> str | None:
    """The screen a node lives on: its file-level node, when that file is a screen doc."""
    file_id = node_id.split("#", 1)[0]
    node = by_id.get(file_id)
    if node is None or node.get("type") != "screen":
        return None
    return file_id


def navigation_edges(data: dict) -> list[dict]:
    """Every documented screen-to-screen transition, with the action that causes it.

    Two sources, deliberately kept distinct in ``kind`` so a caller can prefer one: a ``leads-to:``
    component is a single click, while a flow step arrives with whatever state the earlier steps
    established — cheaper to trust, harder to replay in isolation.
    """
    by_id = {n["id"]: n for n in data["nodes"]}
    edges: list[dict] = []

    for node in data["nodes"]:
        src = _screen_of(node["id"], by_id)
        if src is None:
            continue
        for edge in node["edges"]:
            if edge["via"] != NAV_BULLET:
                continue
            dst = _screen_of(edge["to"], by_id)
            if dst is None or dst == src:
                continue  # an intra-screen `leads-to:` is a state change, not navigation
            edges.append({
                "from": src, "to": dst, "kind": "leads-to",
                "action": "activate", "node": node["id"], "label": node["title"],
            })

    for node in data["nodes"]:
        if node["type"] != "flow":
            continue
        prev_screen: str | None = None
        prev_step: dict | None = None
        for edge in node["edges"]:
            if edge["via"] != STEP_BULLET:
                continue
            screen = _screen_of(edge["to"], by_id)
            if screen is None:
                continue  # a step pointing at a concept/API doc, not at a screen
            if prev_screen is not None and prev_screen != screen and prev_step is not None:
                edges.append({
                    "from": prev_screen, "to": screen, "kind": "flow-step",
                    "action": "interact", "node": prev_step["to"],
                    "label": prev_step["text"], "flow": node["id"],
                })
            prev_screen, prev_step = screen, edge

    return edges


def _index(edges: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for edge in edges:
        out.setdefault(edge["from"], []).append(edge)
    return out


def route(edges: list[dict], start: str, target: str,
          by_id: dict | None = None) -> list[dict] | None:
    """The shortest documented click-path from *start* to *target*, or None if there is none.

    Breadth-first, so the route is the fewest hops the book describes. ``leads-to:`` edges sort
    ahead of flow steps at equal depth: a single click replays more reliably than a journey
    prefix whose earlier steps have to be re-established.

    With *by_id* (the node index from ``graph.build``) each hop carries the destination screen's
    preconditions, so a caller walking the route knows what to satisfy before each arrival.
    """
    if start == target:
        return []

    def _hop(edge: dict) -> dict:
        if by_id is None:
            return edge
        return {**edge, "preconditions": preconditions(by_id.get(edge["to"], {}))}

    by_from = _index(edges)
    queue: deque[tuple[str, list[dict]]] = deque([(start, [])])
    seen = {start}
    while queue:
        node, path = queue.popleft()
        outgoing = sorted(by_from.get(node, []), key=lambda e: e["kind"] != "leads-to")
        for edge in outgoing:
            nxt = edge["to"]
            if nxt in seen:
                continue
            hop = [*path, _hop(edge)]
            if nxt == target:
                return hop
            seen.add(nxt)
            queue.append((nxt, hop))
    return None


def screens_of(data: dict) -> list[str]:
    return [n["id"] for n in data["nodes"] if n["type"] == "screen" and n["kind"] == "file"]


def is_route(value: str) -> bool:
    """Whether an ``entry:`` value is an address a walk can open, rather than a description."""
    return value.startswith("/") or bool(re.match(r"https?://", value))


#: Why `is_route` said no, in the book's own terms — kept beside the predicate it describes so
#: a caller reporting the reason and a change to the rule stay one edit apart, not two files.


def _norm_path(path: str) -> str:
    """A route or URL path, comparable: no backticks, no trailing slash except on the root."""
    path = path.strip().strip("`").strip()
    return path if path == ROOT_PATH else path.rstrip("/") or ROOT_PATH


def root_path(data: dict, driver: str | None = None) -> tuple[str | None, str | None]:
    """``(path, server)`` — where the surface is entered, and the server contract that says so.

    The server marked ``walkthrough: true`` wins; a sole server stands in for it; several
    unmarked ones resolve to no contract, because a root read off an arbitrary pick is a root
    the walk will not open. With no contract the root is ``/``, which is what the doctor's
    ``runbook-missing`` already asks the book to state.

    *driver* is the surface's declared ``driver:`` (``surface_driver``), when the caller
    already knows it. A driver `routes.is_path_addressed` says has no path grammar — today,
    ``mobile`` — has no root *path* to state at all: ``(None, None)``, rather than inventing
    ``/`` for a navigator that routes on names. Every other driver, including an undeclared one
    (``driver=None``), keeps the grammar above unchanged.
    """
    if not routes_mod.is_path_addressed(driver):
        return None, None
    servers = [n for n in data["nodes"] if n["type"] == SERVER_TYPE and n["kind"] == "file"]
    marked = [n for n in servers
              if bullet_value(n["bullets"], WALKTHROUGH_BULLET).lower() in ("true", "yes")]
    chosen = marked[0] if len(marked) == 1 else (servers[0] if len(servers) == 1 else None)
    if chosen is None:
        return ROOT_PATH, None
    url = bullet_value(chosen["bullets"], ENTRY_URL_BULLET)
    return _norm_path(urlparse(url).path if url else ROOT_PATH), chosen["id"]


RUNBOOK_TYPE = "runbook"
SURFACES_BULLET = "surfaces"


class ConflictingEntryOrigin(ValueError):
    """More than one book source states a different origin for the same surface's entry URL."""

    def __init__(self, surface: str, origins: list[tuple[str, str]]) -> None:
        self.surface = surface
        self.origins = origins  # [(node_id, origin), ...], in the order each source was found
        named = "; ".join(f"{node} says {origin}" for node, origin in origins)
        super().__init__(f"surface {surface!r} has conflicting entry origins: {named}")


def _origin(url: str) -> str:
    """``scheme://host[:port]`` off a full ``entry-url:`` value; empty when it has none."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""


def entry_origin(dump: dict, surface: str) -> str | None:
    """The ``scheme://host[:port]`` a QA walk should open for *surface*; ``None`` if the book
    states none.

    Two kinds of source state it, and both are read at full-book scope so a runbook filed under
    a different surface than the one it stands up still counts: the surface's own ``server`` node
    (the same one ``root_path`` already selects — the one marked ``walkthrough: true``, or the
    sole server) via its ``entry-url:``; and any ``runbook`` node whose ``surfaces:`` bullet links
    into this surface, via that runbook's own ``entry-url:``. When those sources name more than
    one distinct origin, that is ``ConflictingEntryOrigin`` rather than an arbitrary pick — a
    silently wrong base URL is worse than a compile-time gap.
    """
    by_id = {n["id"]: n for n in dump["nodes"]}
    candidates: list[tuple[str, str]] = []

    surface_dump = graph_mod.subset(dump, surface)
    _path, server_id = root_path(surface_dump)
    if server_id is not None:
        origin = _origin(bullet_value(by_id[server_id]["bullets"], ENTRY_URL_BULLET))
        if origin:
            candidates.append((server_id, origin))

    for node in dump["nodes"]:
        if node["type"] != RUNBOOK_TYPE or node["kind"] != "file":
            continue
        targets = {edge["to"] for edge in node["edges"] if edge["via"] == SURFACES_BULLET}
        if not any(by_id.get(target, {}).get("surface") == surface for target in targets):
            continue
        origin = _origin(bullet_value(node["bullets"], ENTRY_URL_BULLET))
        if origin:
            candidates.append((node["id"], origin))

    origins = sorted({origin for _node, origin in candidates})
    if len(origins) > 1:
        raise ConflictingEntryOrigin(surface, candidates)
    return origins[0] if origins else None


DRIVER_BULLET = "driver"
BUNDLE_ID_BULLET = "bundle-id"
LAUNCH_SCREEN_BULLET = "launch-screen"


class UnsettledSurfaceDriver(ValueError):
    """The book does not settle which `driver:` exercises a surface.

    Base of every reason `surface_driver` refuses to answer, so that a reader wanting a
    *grammar* degrades to an undeclared driver by catching this one class and stays correct
    when a further reason is added. Only the two checks whose job is to report the book
    catch the subclasses, because the remedies differ and a reader that cannot tell them
    apart would send the author after the wrong bullet.
    """


class ConflictingSurfaceDriver(UnsettledSurfaceDriver):
    """More than one runbook marked ``walkthrough: true`` states a different `driver:` for the
    same surface."""

    def __init__(self, surface: str, drivers: list[tuple[str, str]]) -> None:
        self.surface = surface
        self.drivers = drivers  # [(node_id, driver), ...], in the order each source was found
        named = "; ".join(f"{node} says {driver}" for node, driver in drivers)
        super().__init__(f"surface {surface!r} has conflicting drivers: {named}")


class UndeclaredWalkthroughRunbook(UnsettledSurfaceDriver):
    """Several runbooks cover one surface and none of them claims to be the walkthrough."""

    def __init__(self, surface: str, drivers: list[tuple[str, str]]) -> None:
        self.surface = surface
        self.drivers = drivers
        named = "; ".join(f"{node} drives it with {driver}" for node, driver in drivers)
        super().__init__(
            f"surface {surface!r} is covered by several runbooks and none is marked "
            f"`walkthrough: true`: {named}"
        )


def surface_driver(dump: dict, surface: str) -> str | None:
    """The `driver:` of the runbook that exercises *surface*; ``None`` if no runbook covers it.

    A runbook's `driver:` states what that runbook drives — that alone says nothing about
    which runbook is *how the surface is exercised*. A real surface routinely has several
    runbooks (a lint runbook with `driver: cli`, a browser runbook with `driver: web`, an IaC
    runbook with `driver: iac`) all correctly naming this surface through `surfaces:`; that is
    not a disagreement to resolve, it is several true claims. Read the same way `root_path`
    picks the one server that stands for a surface: the runbook marked ``walkthrough: true``
    wins, a sole runbook stands in for it, and several unmarked ones with different drivers
    resolve to no answer — `UndeclaredWalkthroughRunbook`, because dispatching off an arbitrary
    pick is worse than a compile-time gap. Two runbooks *both* marked ``walkthrough: true`` that
    still disagree is `ConflictingSurfaceDriver`.
    """
    by_id = {n["id"]: n for n in dump["nodes"]}
    candidates: list[tuple[str, str]] = []

    for node in dump["nodes"]:
        if node["type"] != RUNBOOK_TYPE or node["kind"] != "file":
            continue
        targets = {edge["to"] for edge in node["edges"] if edge["via"] == SURFACES_BULLET}
        if not any(by_id.get(target, {}).get("surface") == surface for target in targets):
            continue
        driver = bullet_value(node["bullets"], DRIVER_BULLET).strip().lower()
        if driver:
            candidates.append((node["id"], driver))

    marked = [(node, driver) for node, driver in candidates
              if bullet_value(by_id[node]["bullets"], WALKTHROUGH_BULLET).lower()
              in ("true", "yes")]
    if marked:
        marked_drivers = sorted({driver for _node, driver in marked})
        if len(marked_drivers) > 1:
            raise ConflictingSurfaceDriver(surface, marked)
        return marked_drivers[0]

    drivers = sorted({driver for _node, driver in candidates})
    if len(drivers) > 1:
        raise UndeclaredWalkthroughRunbook(surface, candidates)
    return drivers[0] if drivers else None


class UnsettledSurfaceBundleId(ValueError):
    """The book does not settle which `bundle-id:` addresses a surface.

    Base of every reason `surface_bundle_id` refuses to answer, mirroring
    `UnsettledSurfaceDriver` — a reader wanting a bundle id degrades to an undeclared one by
    catching this one class and stays correct when a further reason is added.
    """


class ConflictingSurfaceBundleId(UnsettledSurfaceBundleId):
    """More than one runbook marked ``walkthrough: true`` states a different `bundle-id:` for
    the same surface."""

    def __init__(self, surface: str, bundle_ids: list[tuple[str, str]]) -> None:
        self.surface = surface
        self.bundle_ids = bundle_ids  # [(node_id, bundle_id), ...], found-order
        named = "; ".join(f"{node} says {bundle_id}" for node, bundle_id in bundle_ids)
        super().__init__(f"surface {surface!r} has conflicting bundle ids: {named}")


class UndeclaredWalkthroughBundleIdRunbook(UnsettledSurfaceBundleId):
    """Several runbooks cover one surface and none of them claims to be the walkthrough."""

    def __init__(self, surface: str, bundle_ids: list[tuple[str, str]]) -> None:
        self.surface = surface
        self.bundle_ids = bundle_ids
        named = "; ".join(f"{node} states {bundle_id}" for node, bundle_id in bundle_ids)
        super().__init__(
            f"surface {surface!r} is covered by several runbooks and none is marked "
            f"`walkthrough: true`: {named}"
        )


def surface_bundle_id(dump: dict, surface: str) -> str | None:
    """The `bundle-id:` of the runbook that exercises *surface*; ``None`` if none covers it.

    Cloned from `surface_driver`: several runbooks legitimately name the same surface through
    `surfaces:`, so that alone is not a disagreement. The runbook marked ``walkthrough: true``
    wins; a sole runbook stands in for it; several unmarked ones with different bundle ids
    resolve to no answer — `UndeclaredWalkthroughBundleIdRunbook`, because dispatching off an
    arbitrary pick is worse than a compile-time gap. Two runbooks *both* marked
    ``walkthrough: true`` that still disagree is `ConflictingSurfaceBundleId`.
    """
    by_id = {n["id"]: n for n in dump["nodes"]}
    candidates: list[tuple[str, str]] = []

    for node in dump["nodes"]:
        if node["type"] != RUNBOOK_TYPE or node["kind"] != "file":
            continue
        targets = {edge["to"] for edge in node["edges"] if edge["via"] == SURFACES_BULLET}
        if not any(by_id.get(target, {}).get("surface") == surface for target in targets):
            continue
        bundle_id = bullet_value(node["bullets"], BUNDLE_ID_BULLET).strip()
        if bundle_id:
            candidates.append((node["id"], bundle_id))

    marked = [(node, bundle_id) for node, bundle_id in candidates
              if bullet_value(by_id[node]["bullets"], WALKTHROUGH_BULLET).lower()
              in ("true", "yes")]
    if marked:
        marked_bundle_ids = sorted({bundle_id for _node, bundle_id in marked})
        if len(marked_bundle_ids) > 1:
            raise ConflictingSurfaceBundleId(surface, marked)
        return marked_bundle_ids[0]

    bundle_ids = sorted({bundle_id for _node, bundle_id in candidates})
    if len(bundle_ids) > 1:
        raise UndeclaredWalkthroughBundleIdRunbook(surface, candidates)
    return bundle_ids[0] if bundle_ids else None


class UnsettledSurfaceLaunchScreen(ValueError):
    """The book does not settle which screen `launch-screen:` names for a surface.

    Base of every reason `surface_launch_screen` refuses to answer, mirroring
    `UnsettledSurfaceDriver`/`UnsettledSurfaceBundleId` — a reader wanting a launch screen
    degrades to an undeclared one by catching this one class and stays correct when a further
    reason is added.
    """


class ConflictingSurfaceLaunchScreen(UnsettledSurfaceLaunchScreen):
    """More than one runbook marked ``walkthrough: true`` states a different `launch-screen:`
    for the same surface."""

    def __init__(self, surface: str, screens: list[tuple[str, str]]) -> None:
        self.surface = surface
        self.screens = screens
        named = "; ".join(f"{node} says {screen}" for node, screen in screens)
        super().__init__(f"surface {surface!r} has conflicting launch screens: {named}")


class UndeclaredWalkthroughLaunchScreenRunbook(UnsettledSurfaceLaunchScreen):
    """Several runbooks cover one surface and none of them claims to be the walkthrough."""

    def __init__(self, surface: str, screens: list[tuple[str, str]]) -> None:
        self.surface = surface
        self.screens = screens
        named = "; ".join(f"{node} states {screen}" for node, screen in screens)
        super().__init__(
            f"surface {surface!r} is covered by several runbooks and none is marked "
            f"`walkthrough: true`: {named}"
        )


def surface_launch_screen(dump: dict, surface: str) -> str | None:
    """The screen `launch-screen:` names for the runbook that exercises *surface*; ``None`` if
    none covers it.

    Cloned from `surface_bundle_id`, with one difference: `launch-screen:` is authored as a
    markdown link (the same way `surfaces:` is), not a bare string, since it names another
    node rather than stating a literal value — so this reads the link's own href out of
    `bullet_value` and resolves it against the node's own edges by href, rather than by
    `edge["via"]`: a node whose `launch-screen:` points at a screen already named in its own
    `surfaces:` shares that href with the `surfaces:` edge, and `graph._edge_sources` tags the
    first bullet to claim an href as every edge's `via` for that href — matching by href instead
    survives that collision, since every edge sharing an href resolves to the same target
    regardless of which bullet is credited. The returned string is the target document's path
    with no `#anchor`, the same spelling `screen_routes()` keys on and obligations carry as
    `source`, so a caller can compare the two directly. The runbook marked ``walkthrough: true``
    wins; a sole runbook stands in for it; several unmarked ones with different launch screens
    resolve to no answer — `UndeclaredWalkthroughLaunchScreenRunbook`, because dispatching off
    an arbitrary pick is worse than a compile-time gap. Two runbooks *both* marked
    ``walkthrough: true`` that still disagree is `ConflictingSurfaceLaunchScreen`.
    """
    by_id = {n["id"]: n for n in dump["nodes"]}
    candidates: list[tuple[str, str]] = []

    for node in dump["nodes"]:
        if node["type"] != RUNBOOK_TYPE or node["kind"] != "file":
            continue
        targets = {edge["to"] for edge in node["edges"] if edge["via"] == SURFACES_BULLET}
        if not any(by_id.get(target, {}).get("surface") == surface for target in targets):
            continue
        launch_screen_raw = bullet_value(node["bullets"], LAUNCH_SCREEN_BULLET).strip()
        launch_screen_links = markdown.extract_refs(launch_screen_raw).links
        if launch_screen_links:
            _text, href = launch_screen_links[0]
            launch_targets = {edge["to"] for edge in node["edges"] if edge["href"] == href}
            if launch_targets:
                screen = sorted(launch_targets)[0].split("#")[0]
                candidates.append((node["id"], screen))

    marked = [(node, screen) for node, screen in candidates
              if bullet_value(by_id[node]["bullets"], WALKTHROUGH_BULLET).lower()
              in ("true", "yes")]
    if marked:
        marked_screens = sorted({screen for _node, screen in marked})
        if len(marked_screens) > 1:
            raise ConflictingSurfaceLaunchScreen(surface, marked)
        return marked_screens[0]

    screens = sorted({screen for _node, screen in candidates})
    if len(screens) > 1:
        raise UndeclaredWalkthroughLaunchScreenRunbook(surface, candidates)
    return screens[0] if screens else None


def root_screen(data: dict, driver: str | None = None) -> str | None:
    """The screen whose ``route:`` is the surface's root path — the one node a walk starts on.

    ``None`` both when no screen's ``route:`` matches (a real book gap) and when *driver* has
    no path grammar to match against at all (``root_path`` already said so by returning no
    path) — the two are told apart by the caller, which already has *driver* to ask again.
    """
    path, _ = root_path(data, driver)
    if path is None:
        return None
    for node in data["nodes"]:
        if node["type"] != "screen" or node["kind"] != "file":
            continue
        if _norm_path(bullet_value(node["bullets"], ROUTE_BULLET)) == path:
            return node["id"]
    return None


def route_entries(data: dict) -> list[str]:
    """Screens whose ``entry:`` states a route — the deep links that seed the traversal too."""
    return [n["id"] for n in data["nodes"]
            if n["type"] == "screen" and n["kind"] == "file"
            and is_route(bullet_value(n["bullets"], ENTRY_BULLET))]


def prose_entry(node: dict) -> str:
    """The ``entry:`` value when it describes rather than addresses; empty otherwise."""
    value = bullet_value(node["bullets"], ENTRY_BULLET)
    return "" if not value or is_route(value) else value


def reachable_from(edges: list[dict], starts: list[str]) -> set[str]:
    """Every screen reachable by clicking from any of *starts*."""
    by_from = _index(edges)
    seen = set(starts)
    queue = deque(starts)
    while queue:
        for edge in by_from.get(queue.popleft(), []):
            if edge["to"] not in seen:
                seen.add(edge["to"])
                queue.append(edge["to"])
    return seen


NO_PATH_ROOT = "no-path-root"
NO_SURFACE = "no-surface"
UNSETTLED_LAUNCH_SCREEN = "unsettled-launch-screen"
NO_LAUNCH_SCREEN = "no-launch-screen"
LAUNCH_SCREEN_NOT_SCREEN = "launch-screen-not-screen"


def surface_root(data: dict, driver: str | None = None, *,
                 surface: str | None = None
                 ) -> tuple[str | None, str, UnsettledSurfaceLaunchScreen | str | None]:
    """``(root, reason, detail)`` — the start screen, why there is none, and the evidence for why.

    *reason* is ``""`` on success, else one of the five stable tokens above, each naming exactly
    one of the ways a surface can fail to state where it starts. A path-addressed driver
    (`routes.is_path_addressed`) is answered the way it always has been — a screen whose
    ``route:`` is the surface's root path (`root_screen`/`root_path`), or ``NO_PATH_ROOT`` when
    no screen's does. A driver with no path grammar has no root *path* to consult at all, so it
    is answered from `launch-screen:` instead, read via `surface_launch_screen` — which needs
    *surface* to know which runbook to ask, hence ``NO_SURFACE`` when the caller has not given
    one. That bullet is then reported in its own words exactly as it can fail: unsettled between
    walkthrough runbooks (``UNSETTLED_LAUNCH_SCREEN``), stated nowhere (``NO_LAUNCH_SCREEN``), or
    naming something that is not a screen on this surface (``LAUNCH_SCREEN_NOT_SCREEN``).

    *detail* is the evidence a caller needs to render the failure without asking the question
    again: the caught `UnsettledSurfaceLaunchScreen` itself for ``UNSETTLED_LAUNCH_SCREEN`` (kept
    as the exception, not its text, so a caller that wants `raise ... from` still can), the
    offending launch-screen id for ``LAUNCH_SCREEN_NOT_SCREEN``, and ``None`` for every other
    reason — the other three name a fact that needs no further grounding.

    This is the one place that decision is made; `resolve_start` and `unreachable_screens` both
    read it rather than each drawing the distinctions again.
    """
    if routes_mod.is_path_addressed(driver):
        root = root_screen(data, driver)
        return (root, "", None) if root is not None else (None, NO_PATH_ROOT, None)
    if surface is None:
        return None, NO_SURFACE, None
    try:
        launch_screen = surface_launch_screen(data, surface)
    except UnsettledSurfaceLaunchScreen as exc:
        return None, UNSETTLED_LAUNCH_SCREEN, exc
    if launch_screen is None:
        return None, NO_LAUNCH_SCREEN, None
    if launch_screen not in screens_of(data):
        return None, LAUNCH_SCREEN_NOT_SCREEN, launch_screen
    return launch_screen, "", None


def unreachable_screens(data: dict, driver: str | None = None, *,
                        surface: str | None = None
                        ) -> tuple[list[str], str | None, list[str], str]:
    """``(unreachable, root, seeds, reason)``. A ``None`` root means the check could not run.

    A ``None`` root is not the same as a pass; *reason* is the `surface_root` token that says why
    there is none, so a caller that must report the failure does not have to ask `surface_root`
    the same question again. It is ``""`` when *root* is not ``None``.

    Reachability is transitive, so this is deliberately not "has an inbound edge": a cluster of
    screens that link to each other but hangs off nothing is exactly the shape a broken navigation
    graph takes, and an inbound-degree test scores every member of it as fine. And it starts from
    the root rather than from every ``entry:``, because an exemption is a claim about the outside
    world an edge check cannot verify — eight screens each saying "entered from outside" is a
    book with no navigation in it, passing.

    *driver* and *surface* thread through to `surface_root` — see there for what a driver with
    no path grammar does, and what *surface* is for.
    """
    root, reason, _detail = surface_root(data, driver, surface=surface)
    if root is None:
        return [], None, [], reason
    seeds = sorted({root, *route_entries(data)})
    reached = reachable_from(navigation_edges(data), seeds)
    return sorted(set(screens_of(data)) - reached), root, seeds, ""


class UnknownStart(ValueError):
    """The requested start names no screen on the surface."""


def resolve_start(data: dict, start: str | None, driver: str | None = None, *,
                  surface: str | None = None) -> str:
    """*start* as a screen id, or the surface's root when none was given.

    A surface with no screens at all is told that directly: a search that finds nothing because
    there was nothing to find is a different fact from a search that finds nothing because the
    thing it wanted was missing, and `launch-screen:`, `--from` and a root path are all repairs
    for the latter — none of them names anything when there is no screen to point at.

    *driver* decides which of the two ``root_screen`` failures this is. A driver with no path
    grammar — `mobile` names its screens, `cli` routes nothing — has no root path to state, but
    when *surface* is given it may still state where it starts via `launch-screen:`, so that is
    consulted first; only when that bullet is silent, unsettled, or names something that is not
    a screen on the surface is the caller told so, rather than sent looking for a screen at `/`.
    Each of those three is reported in its own words: a message that says the book stated
    nothing, where the book stated something unusable, sends the reader to the wrong line.
    """
    screens = screens_of(data)
    if start is None:
        if not screens:
            named = f"a `{driver}` surface" if driver else "this surface"
            raise UnknownStart(f"{named} declares no screens; there is nothing to start from")
        root, reason, detail = surface_root(data, driver, surface=surface)
        if root is None:
            named = f"a `{driver}` surface" if driver else "this surface"
            if reason == NO_PATH_ROOT:
                path, _ = root_path(data, driver)
                raise UnknownStart(f"no screen's `route:` is the root path {path}; pass --from")
            if reason == UNSETTLED_LAUNCH_SCREEN:
                cause = detail if isinstance(detail, UnsettledSurfaceLaunchScreen) else None
                raise UnknownStart(
                    f"{named} has an unsettled `launch-screen:`: {detail}"
                ) from cause
            if reason == LAUNCH_SCREEN_NOT_SCREEN:
                raise UnknownStart(
                    f"{named} states `launch-screen:` {detail}, which is not a "
                    "screen on this surface; pass --from"
                )
            if reason == NO_LAUNCH_SCREEN:
                raise UnknownStart(
                    f"{named} states no `launch-screen:` on its runbook and no root path "
                    "to start from; pass --from"
                )
            raise UnknownStart(f"{named} states no root path to start from; pass --from")
        return root
    if start in screens:
        return start
    hint = next((sid for sid in screens if sid.endswith(f"/{start}.md")), None)
    raise UnknownStart(f"{start} is not a screen on this surface"
                       + (f" — did you mean {hint}?" if hint else ""))


def reachability(graph: Graph, *, surface: str | None = None, start: str | None = None,
                 driver: str | None = None) -> dict:
    """Route every documented screen on *surface* from *start*; report the ones with no path.

    *start* defaults to the surface's root screen — or, for a surface with no path grammar, its
    `launch-screen:` — and a start that names no screen raises rather than routing from nowhere:
    a typo in ``--from`` used to yield "0 reachable" — every screen reported as a hole in the
    book, with the book untouched.
    The unreachable list is the actionable half: each entry is a screen the book documents but
    never says how to arrive at, which is exactly the missing coverage a walk cannot close on its own.
    """
    data = graph_mod.build(graph, surface=surface)
    by_id = {n["id"]: n for n in data["nodes"]}
    edges = navigation_edges(data)
    screens = screens_of(data)
    start = resolve_start(data, start, driver, surface=surface)

    routed: dict[str, list[dict]] = {}
    unreachable: list[str] = []
    undeclared: list[str] = []
    for screen in screens:
        if not preconditions(by_id[screen])["declared"]:
            undeclared.append(screen)
        path = route(edges, start, screen, by_id)
        if path is None:
            unreachable.append(screen)
        else:
            routed[screen] = path

    return {
        "start": start,
        "surface": surface or "",
        "counts": {
            "screens": len(screens),
            "reachable": len(routed),
            "unreachable": len(unreachable),
            "undeclared": len(undeclared),
            "nav_edges": len(edges),
        },
        "routes": routed,
        "unreachable": sorted(unreachable),
        # Reachable but with no declared preconditions: the walk can get there and still not
        # know what state it needs, so these are not "done" either.
        "undeclared": sorted(undeclared),
    }


def render_route(path: list[dict], start: str, target: str) -> str:
    """One line per hop: the screen you leave, what you activate, where you land."""
    if not path:
        return f"{start} is the target"
    lines = [f"{start}"]
    for i, hop in enumerate(path, 1):
        lines.append(f"  {i}. {hop['action']} {hop['label']}  [{hop['kind']}]")
        lines.append(f"     -> {hop['to']}")
        pre = hop.get("preconditions")
        if pre is None:
            continue
        if not pre["declared"]:
            lines.append("        ! preconditions undeclared")
            continue
        for guard in pre["guards"]:
            lines.append(f"        requires {guard['text']}")
        for param in pre["params"]:
            lines.append(f"        param {param['name']} <- {param['text']}")
    lines.append(f"reached {target} in {len(path)} hop(s)")
    return "\n".join(lines)


def render_reachability(data: dict) -> str:
    counts = data["counts"]
    lines = [
        f"{counts['reachable']}/{counts['screens']} screens reachable from {data['start']} "
        f"({counts['nav_edges']} navigation edges); "
        f"{counts['undeclared']} with undeclared preconditions",
    ]
    for screen in data["unreachable"]:
        lines.append(f"  unreachable  {screen}")
    for screen in data["undeclared"]:
        lines.append(f"  undeclared   {screen}")
    return "\n".join(lines)
