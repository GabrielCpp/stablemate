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

from ostler import graph as graph_mod, markdown
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
        name, _, source = raw.partition(":")
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


def _norm_path(path: str) -> str:
    """A route or URL path, comparable: no backticks, no trailing slash except on the root."""
    path = path.strip().strip("`").strip()
    return path if path == ROOT_PATH else path.rstrip("/") or ROOT_PATH


def root_path(data: dict) -> tuple[str, str | None]:
    """``(path, server)`` — where the surface is entered, and the server contract that says so.

    The server marked ``walkthrough: true`` wins; a sole server stands in for it; several
    unmarked ones resolve to no contract, because a root read off an arbitrary pick is a root
    the walk will not open. With no contract the root is ``/``, which is what the doctor's
    ``runbook-missing`` already asks the book to state.
    """
    servers = [n for n in data["nodes"] if n["type"] == SERVER_TYPE and n["kind"] == "file"]
    marked = [n for n in servers
              if bullet_value(n["bullets"], WALKTHROUGH_BULLET).lower() in ("true", "yes")]
    chosen = marked[0] if len(marked) == 1 else (servers[0] if len(servers) == 1 else None)
    if chosen is None:
        return ROOT_PATH, None
    url = bullet_value(chosen["bullets"], ENTRY_URL_BULLET)
    return _norm_path(urlparse(url).path if url else ROOT_PATH), chosen["id"]


def root_screen(data: dict) -> str | None:
    """The screen whose ``route:`` is the surface's root path — the one node a walk starts on."""
    path, _ = root_path(data)
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


def unreachable_screens(data: dict) -> tuple[list[str], str | None, list[str]]:
    """``(unreachable, root, seeds)``. A ``None`` root means the check could not run, not a pass.

    Reachability is transitive, so this is deliberately not "has an inbound edge": a cluster of
    screens that link to each other but hangs off nothing is exactly the shape a broken navigation
    graph takes, and an inbound-degree test scores every member of it as fine. And it starts from
    the root rather than from every ``entry:``, because an exemption is a claim about the outside
    world an edge check cannot verify — eight screens each saying "entered from outside" is a
    book with no navigation in it, passing.
    """
    root = root_screen(data)
    if root is None:
        return [], None, []
    seeds = sorted({root, *route_entries(data)})
    reached = reachable_from(navigation_edges(data), seeds)
    return sorted(set(screens_of(data)) - reached), root, seeds


class UnknownStart(ValueError):
    """The requested start names no screen on the surface."""


def resolve_start(data: dict, start: str | None) -> str:
    """*start* as a screen id, or the surface's root when none was given."""
    screens = screens_of(data)
    if start is None:
        root = root_screen(data)
        if root is None:
            path, _ = root_path(data)
            raise UnknownStart(f"no screen's `route:` is the root path {path}; pass --from")
        return root
    if start in screens:
        return start
    hint = next((sid for sid in screens if sid.endswith(f"/{start}.md")), None)
    raise UnknownStart(f"{start} is not a screen on this surface"
                       + (f" — did you mean {hint}?" if hint else ""))


def reachability(graph: Graph, *, surface: str | None = None, start: str | None = None) -> dict:
    """Route every documented screen on *surface* from *start*; report the ones with no path.

    *start* defaults to the surface's root screen, and a start that names no screen raises rather
    than routing from nowhere: a typo in ``--from`` used to yield "0 reachable" — every screen
    reported as a hole in the book, with the book untouched.
    The unreachable list is the actionable half: each entry is a screen the book documents but
    never says how to arrive at, which is exactly the missing coverage a walk cannot close on its own.
    """
    data = graph_mod.build(graph, surface=surface)
    by_id = {n["id"]: n for n in data["nodes"]}
    edges = navigation_edges(data)
    screens = screens_of(data)
    start = resolve_start(data, start)

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
