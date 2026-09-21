"""``ostler graph`` — dump the whole OKF graph (nodes + edges + bullets) as JSON to filter on."""
from __future__ import annotations

import re
from pathlib import Path

from ostler import markdown, path as path_mod
from ostler.links import LinkResolver
from ostler.model import Graph, UINode


def _rel(path: Path, root: Path) -> str:
    """*root* is already resolved (``find_root`` resolves once at startup) and every node path is built from it, so a plain ``relative_to`` matches what ``doctor.py`` already trusts for the same computation — re-resolving both sides here paid a realpath syscall per node for no path this codebase ever produces relative or symlinked."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def surface_of(node_path: Path, features_root: Path) -> str:
    """The service a path belongs to: the first path component under ``docs/features/``."""
    try:
        rel = node_path.relative_to(features_root)
    except ValueError:
        return ""
    return rel.parts[0] if rel.parts else ""


def _edge_sources(node: UINode) -> list[str]:
    """For each of ``node.links``, in the same order, the bullet key that owns its line."""
    starts = sorted(node.bullet_lines.items(), key=lambda pair: pair[1])
    key_by_index = {idx: key for key, _raw, idx in node.bullet_order}

    def _held(key: str) -> set[tuple[str, str]]:
        value = node.meta.get(key, "")
        items = value if isinstance(value, list) else [value]
        return {pair for item in items for pair in markdown.extract_refs(str(item)).links}

    def _via(line: int, text: str, href: str) -> str:
        for pos, (idx, start) in enumerate(starts):
            end = starts[pos + 1][1] if pos + 1 < len(starts) else None
            if line < start or (end is not None and line >= end):
                continue
            key = key_by_index.get(idx)
            if key is None or (text, href) not in _held(key):
                return "prose"
            return key
        return "prose"

    return [_via(line, text, href) for text, href, line in node.links]


def _node_dict(node: UINode, resolver: LinkResolver, graph: Graph, features_root: Path,
               path_cache: dict[Path, tuple[str, str]]) -> dict:
    edges = []
    via = _edge_sources(node)
    for (text, href, _line), source in zip(node.links, via, strict=True):
        lt = resolver.resolve(node.path, href)
        if lt is None:
            continue
        edges.append({"text": text, "href": href, "to": lt.node_id, "resolves": lt.resolved,
                      "via": source})
    cached = path_cache.get(node.path)
    if cached is None:
        cached = (_rel(node.path, graph.root), surface_of(node.path, features_root))
        path_cache[node.path] = cached
    rel, surface = cached
    return {
        "id": node.id,
        "type": node.type,
        "kind": node.kind,
        "surface": surface,
        "path": rel,
        "anchor": node.anchor,
        "title": node.title,
        "line": node.line,
        "level": node.level,
        "parent": node.parent,
        "bullets": dict(node.meta),
        "bulletOrder": [list(pair) for pair in node.bullet_order],
        "combiners": {str(pos): word for pos, word in node.combiners.items()},
        "entries": {
            key: [{"headline": entry.headline, "properties": dict(entry.properties)}
                  for entry in items]
            for key, items in node.entries.items() if items
        },
        "edges": edges,
    }


def _paths(node_id: str, by_id: dict) -> tuple[list, list]:
    """Walk `parent` pointers to the root, returning (title_path, type_path) top-down."""
    titles: list = []
    types: list = []
    seen: set = set()
    cur = node_id
    while cur and cur in by_id and cur not in seen:
        seen.add(cur)
        n = by_id[cur]
        titles.append(n.title)
        types.append(n.type)
        cur = n.parent
    return titles[::-1], types[::-1]


def build(graph: Graph, *, etype: str | None = None, surface: str | None = None,
          resolver: LinkResolver | None = None) -> dict:
    """Assemble the graph: every node (with bullets + out-edges) and a flat edge list."""
    if resolver is None:
        resolver = LinkResolver(graph)
    features_root = path_mod.features_root(graph)
    by_id = {n.id: n for n in graph.ui_nodes}
    nodes: list[dict] = []
    edges: list[dict] = []
    path_cache: dict[Path, tuple[str, str]] = {}
    for n in graph.ui_nodes:
        if etype and n.type != etype:
            continue
        d = _node_dict(n, resolver, graph, features_root, path_cache)
        if surface and d["surface"] != surface:
            continue
        d["title_path"], d["type_path"] = _paths(n.id, by_id)
        nodes.append(d)
        for e in d["edges"]:
            edges.append({"from": n.id, "to": e["to"], "text": e["text"],
                          "href": e["href"], "resolves": e["resolves"], "via": e["via"]})
    return {"counts": {"nodes": len(nodes), "edges": len(edges)}, "nodes": nodes, "edges": edges}


def subset(data: dict, surface: str) -> dict:
    """Scope an already-built dump to one surface, without rebuilding it."""
    nodes = [n for n in data["nodes"] if n["surface"] == surface]
    keep = {n["id"] for n in nodes}
    edges = [e for e in data["edges"] if e["from"] in keep]
    return {"counts": {"nodes": len(nodes), "edges": len(edges)}, "nodes": nodes, "edges": edges}


def render_text(data: dict) -> str:
    """Compact human view: a header line, then one line per node with its bullet keys + edge count."""
    lines = [f"{data['counts']['nodes']} nodes, {data['counts']['edges']} edges"]
    for n in data["nodes"]:
        tail = ""
        if n["bullets"]:
            tail += "  bullets:" + ",".join(n["bullets"].keys())
        if n["edges"]:
            tail += f"  edges:{len(n['edges'])}"
        lines.append(f"  [{n['type']}] {n['id']}{tail}")
    return "\n".join(lines)



def _seg_match(seg_type: str, seg_title: str, ntype: str, ntitle: str) -> bool:
    if seg_type and seg_type.lower() != (ntype or "").lower():
        return False
    return not (seg_title and seg_title.lower() not in (ntitle or "").lower())


def _parse_path(expr: str) -> tuple[list[tuple[str, str]], list[str]]:
    """`concept:agent / field:timeout` → ([(type,title), …], ['/', …])."""
    parts = re.split(r"\s*(/|>)\s*", expr.strip())
    segs: list[tuple[str, str]] = []
    ops: list[str] = []
    for i, p in enumerate(parts):
        if i % 2:
            ops.append(p)
        else:
            t, sep, ti = p.partition(":")
            segs.append((t.strip(), ti.strip()) if sep else ("", p.strip()))
    return segs, ops


def _match_path(node: dict, segs: list[tuple[str, str]], ops: list[str]) -> bool:
    """The node's ancestor chain (type_path/title_path) matches the path, right-anchored on the node itself."""
    chain = list(zip(node.get("type_path", []), node.get("title_path", [])))
    if not segs or not chain or not _seg_match(*segs[-1], *chain[-1]):
        return False
    pos = len(chain) - 1
    for k in range(len(segs) - 2, -1, -1):
        st, sti = segs[k]
        if ops[k] == ">":
            pos -= 1
            if pos < 0 or not _seg_match(st, sti, *chain[pos]):
                return False
        else:
            hit = next((j for j in range(pos - 1, -1, -1) if _seg_match(st, sti, *chain[j])), -1)
            if hit < 0:
                return False
            pos = hit
    return True


def _hops_to(node: dict, target: str, by_id: dict) -> int | None:
    """Node-hops from *node* up to *target* (1 = direct child), or None if not an ancestor."""
    cur, depth, seen = node["parent"], 1, set()
    while cur and cur in by_id and cur not in seen:
        if cur == target:
            return depth
        seen.add(cur)
        cur = by_id[cur]["parent"]
        depth += 1
    return None


def _root_of(node_id: str, by_id: dict) -> str:
    """The topmost ancestor of *node_id* inside the graph — the page its heading tree hangs from."""
    cur, seen = node_id, set()
    while by_id[cur]["parent"] in by_id and cur not in seen:
        seen.add(cur)
        cur = by_id[cur]["parent"]
    return cur


def _orphan_ids(data: dict) -> set[str]:
    """Pages nothing reaches: no edge lands on the page or on any heading inside it."""
    by_id = {n["id"]: n for n in data["nodes"]}
    reached = {_root_of(e["to"], by_id) for e in data["edges"] if e["to"] in by_id}
    return {n["id"] for n in data["nodes"]
            if n["parent"] not in by_id and n["id"] not in reached}


def select(data: dict, *, node_type: str | None = None, title: str | None = None,
           path: str | None = None, under: str | None = None, depth: int | None = None,
           has_bullet: str | None = None, bullet: str | None = None,
           links_to: str | None = None, orphans: bool = False) -> list:
    """Filter build()'s nodes by any combination of selectors (AND)."""
    nodes = data["nodes"]
    by_id = {n["id"]: n for n in nodes}
    orphan_ids = _orphan_ids(data) if orphans else set()
    segs: list[tuple[str, str]] = []
    ops: list[str] = []
    if path:
        segs, ops = _parse_path(path)
    out = []
    for n in nodes:
        if node_type and n["type"] != node_type:
            continue
        if title and title.lower() not in n["title"].lower():
            continue
        if has_bullet and has_bullet not in n["bullets"]:
            continue
        if bullet:
            k, _, v = bullet.partition("=")
            if v.strip().lower() not in str(n["bullets"].get(k.strip(), "")).lower():
                continue
        if links_to and not any(e["to"] == links_to for e in n["edges"]):
            continue
        if orphans and n["id"] not in orphan_ids:
            continue
        if under is not None:
            hops = _hops_to(n, under, by_id)
            if hops is None or (depth is not None and hops > depth):
                continue
        if segs and not _match_path(n, segs, ops):
            continue
        out.append(n)
    return out


def render_tree(nodes: list) -> str:
    """Indented outline: each node under its level, with a few bullets inline."""
    if not nodes:
        return "(no matching nodes)"
    base = min(n["level"] for n in nodes)
    lines = []
    for n in nodes:
        indent = "  " * max(0, n["level"] - base)
        bl = list(n["bullets"].items())[:3]
        tail = ("  " + " ".join(f"{k}:{str(v)[:34]}" for k, v in bl)) if bl else ""
        lines.append(f"{indent}[{n['type']}] {n['title']}{tail}")
    return "\n".join(lines)


def render_ids(nodes: list) -> str:
    return "\n".join(n["id"] for n in nodes)
