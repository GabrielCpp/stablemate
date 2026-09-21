"""``ostler reach`` — derive how to navigate to a screen, from the book alone."""

from __future__ import annotations

import re

from collections import deque
from urllib.parse import urlparse

from ostler import drivers as drivers_mod, graph as graph_mod, markdown, routes as routes_mod
from ostler.model import Graph
from ostler.qa.runbook import bullet_value

NAV_BULLET = "leads-to"
STEP_BULLET = "steps"
GUARD_BULLET = "requires"
PARAM_BULLET = "params"
ENTRY_BULLET = "entry"
ROUTE_BULLET = "route"
ROOT_PATH = "/"
SERVER_TYPE = "server"
ENTRY_URL_BULLET = "entry-url"
NONE = "none"
NONE_TOKENS = frozenset({NONE, "n/a", "n.a.", "na", "-", "—", "–", ""})


def _values(value: object) -> list[str]:
    """A bullet's values as a flat list — scalar or nested, the caller does not care which."""
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)] if str(value).strip() else []


def _is_none(raw: str) -> bool:
    """Whether a precondition value states "nothing to satisfy"."""
    head = re.split(r"[—:(]", raw.strip(), maxsplit=1)[0]
    return head.strip().lower() in NONE_TOKENS


def preconditions(node: dict) -> dict:
    """What a caller must satisfy before this screen can render."""
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
    """Every documented screen-to-screen transition, with the action that causes it."""
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
                continue
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
                continue
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
    """The shortest documented click-path from *start* to *target*, or None if there is none."""
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


def root_path(data: dict, driver: str | None = None) -> tuple[str | None, str | None]:
    """``(path, server)`` — where the surface is entered, and the server contract that says so."""
    if not routes_mod.is_path_addressed(driver):
        return None, None
    servers = sorted((n for n in data["nodes"]
                      if n["type"] == SERVER_TYPE and n["kind"] == "file"),
                     key=lambda n: n["id"])
    chosen = servers[0] if servers else None
    if chosen is None:
        return ROOT_PATH, None
    url = bullet_value(chosen["bullets"], ENTRY_URL_BULLET)
    return _norm_path(urlparse(url).path if url else ROOT_PATH), chosen["id"]


RUNBOOK_TYPE = "runbook"
SURFACES_BULLET = "surfaces"


def _origin(url: str) -> str:
    """``scheme://host[:port]`` off a full ``entry-url:`` value; empty when it has none."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""


DRIVER_BULLET = "driver"
BUNDLE_ID_BULLET = "bundle-id"
LAUNCH_SCREEN_BULLET = "launch-screen"


def _driver_rank(driver: str) -> int:
    """Where *driver* sits in §4.1's own order; past the end when it names nothing there."""
    try:
        return drivers_mod.DRIVERS.index(driver)
    except ValueError:
        return len(drivers_mod.DRIVERS)


def surface_runbooks(dump: dict, surface: str) -> list[dict]:
    """Every `runbook` node covering *surface*, in the order the engine consults them."""
    by_id = {n["id"]: n for n in dump["nodes"]}
    covering: list[dict] = []
    for node in dump["nodes"]:
        if node["type"] != RUNBOOK_TYPE or node["kind"] != "file":
            continue
        targets = {edge["to"] for edge in node["edges"] if edge["via"] == SURFACES_BULLET}
        if any(by_id.get(target, {}).get("surface") == surface for target in targets):
            covering.append(node)
    return sorted(covering, key=lambda n: (
        _driver_rank(bullet_value(n["bullets"], DRIVER_BULLET).strip().lower()), n["id"]))


def _surface_value(dump: dict, surface: str, key: str) -> str | None:
    """The first non-empty *key* stated by any runbook covering *surface*, in consult order."""
    for node in surface_runbooks(dump, surface):
        value = bullet_value(node["bullets"], key).strip()
        if value:
            return value
    return None


def entry_origin(dump: dict, surface: str) -> str | None:
    """The ``scheme://host[:port]`` a QA walk should open for *surface*; ``None`` if the book states none."""
    origin = _origin(_surface_value(dump, surface, ENTRY_URL_BULLET) or "")
    if origin:
        return origin
    by_id = {n["id"]: n for n in dump["nodes"]}
    _path, server_id = root_path(graph_mod.subset(dump, surface))
    if server_id is None:
        return None
    return _origin(bullet_value(by_id[server_id]["bullets"], ENTRY_URL_BULLET)) or None


def surface_driver(dump: dict, surface: str) -> str | None:
    """The `driver:` of the runbook that exercises *surface*; ``None`` if none states one."""
    driver = _surface_value(dump, surface, DRIVER_BULLET)
    return driver.lower() if driver else None


def surface_bundle_id(dump: dict, surface: str) -> str | None:
    """The `bundle-id:` a Maestro flow launches for *surface*; ``None`` if none states one."""
    return _surface_value(dump, surface, BUNDLE_ID_BULLET)


def surface_launch_screen(dump: dict, surface: str) -> str | None:
    """The screen `launch-screen:` names for *surface*; ``None`` if no runbook names one."""
    for node in surface_runbooks(dump, surface):
        raw = bullet_value(node["bullets"], LAUNCH_SCREEN_BULLET).strip()
        links = markdown.extract_refs(raw).links
        if not links:
            continue
        _text, href = links[0]
        targets = {edge["to"] for edge in node["edges"] if edge["href"] == href}
        if targets:
            return sorted(targets)[0].split("#")[0]
    return None


def root_screen(data: dict, driver: str | None = None) -> str | None:
    """The screen whose ``route:`` is the surface's root path — the one node a walk starts on."""
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
NO_LAUNCH_SCREEN = "no-launch-screen"
LAUNCH_SCREEN_NOT_SCREEN = "launch-screen-not-screen"


def surface_root(data: dict, driver: str | None = None, *,
                 surface: str | None = None
                 ) -> tuple[str | None, str, str | None]:
    """``(root, reason, detail)`` — the start screen, why there is none, and the evidence for why."""
    if routes_mod.is_path_addressed(driver):
        root = root_screen(data, driver)
        return (root, "", None) if root is not None else (None, NO_PATH_ROOT, None)
    if surface is None:
        return None, NO_SURFACE, None
    launch_screen = surface_launch_screen(data, surface)
    if launch_screen is None:
        return None, NO_LAUNCH_SCREEN, None
    if launch_screen not in screens_of(data):
        return None, LAUNCH_SCREEN_NOT_SCREEN, launch_screen
    return launch_screen, "", None


def unreachable_screens(data: dict, driver: str | None = None, *,
                        surface: str | None = None
                        ) -> tuple[list[str], str | None, list[str], str]:
    """``(unreachable, root, seeds, reason)``."""
    root, reason, _detail = surface_root(data, driver, surface=surface)
    if root is None:
        return [], None, [], reason
    seeds = sorted({root, *route_entries(data)})
    reached = reachable_from(navigation_edges(data), seeds)
    return sorted(set(screens_of(data)) - reached), root, seeds, ""


class UnknownStart(ValueError):
    """The requested start names no screen on the surface."""


class NoScreens(UnknownStart):
    """*start* was ``None`` and the surface declares no screens at all."""


def resolve_start(data: dict, start: str | None, driver: str | None = None, *,
                  surface: str | None = None) -> str:
    """*start* as a screen id, or the surface's root when none was given."""
    screens = screens_of(data)
    if start is None:
        if not screens:
            named = f"a `{driver}` surface" if driver else "this surface"
            raise NoScreens(f"{named} declares no screens; there is nothing to start from")
        root, reason, detail = surface_root(data, driver, surface=surface)
        if root is None:
            named = f"a `{driver}` surface" if driver else "this surface"
            if reason == NO_PATH_ROOT:
                path, _ = root_path(data, driver)
                raise UnknownStart(f"no screen's `route:` is the root path {path}; pass --from")
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
    """Route every documented screen on *surface* from *start*; report the ones with no path."""
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
