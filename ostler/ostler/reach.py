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

from collections import deque

from ostler import graph as graph_mod, markdown
from ostler.model import Graph

# The one bullet that means "activating this moves the user to that screen". `extends:`/`parent:`
# are structure and `on:` is attachment; none of them are things a user can do.
NAV_BULLET = "leads-to"
STEP_BULLET = "steps"
GUARD_BULLET = "requires"
PARAM_BULLET = "params"
# The literal that means "declared, and empty". Anything else is a real precondition.
NONE = "none"


def _values(value: object) -> list[str]:
    """A bullet's values as a flat list — scalar or nested, the caller does not care which."""
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)] if str(value).strip() else []


def preconditions(node: dict) -> dict:
    """What a caller must satisfy before this screen can render.

    ``declared`` is the honest bit: False means the bullets are missing, which is *not* the same
    as unconditional. Callers must treat an undeclared screen as unverifiable rather than free.
    """
    meta = node.get("bullets", {})
    guards, params = [], []
    for raw in _values(meta.get(GUARD_BULLET, "")):
        if raw.strip().lower() == NONE:
            continue
        links = markdown.extract_refs(raw).links
        guards.append({"text": raw.strip(), "node": links[0][1] if links else ""})
    for raw in _values(meta.get(PARAM_BULLET, "")):
        if raw.strip().lower() == NONE:
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


def reachability(graph: Graph, *, surface: str | None = None, start: str) -> dict:
    """Route every documented screen on *surface* from *start*; report the ones with no path.

    The unreachable list is the actionable half: each entry is a screen the book documents but
    never says how to arrive at, which is exactly the gap a walk cannot close on its own.
    """
    data = graph_mod.build(graph, surface=surface)
    by_id = {n["id"]: n for n in data["nodes"]}
    edges = navigation_edges(data)
    screens = [n["id"] for n in data["nodes"] if n["type"] == "screen" and n["kind"] == "file"]

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
