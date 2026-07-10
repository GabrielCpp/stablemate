"""``ostler graph`` — dump the whole OKF graph (nodes + edges + bullets) as JSON to filter on.

``list``/``search`` are per-type / full-text and ``trace`` walks out from one node; this emits
*every* UI node together with its parsed ``- key: value`` bullets and its resolved out-edges, plus a
flat edge list. That lets an agent (or ``jq``) filter the graph structurally rather than by prose
match — e.g. the node whose ``code:`` is a given symbol (dedup before enqueue), every
``code:``/``verify:`` bullet (inventory coverage), or the nodes nothing links to (orphans).
"""
from __future__ import annotations

import re
from pathlib import Path

from .links import LinkResolver
from .model import Graph, UINode


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return path.as_posix()


def _surface_of(node: UINode, features_root: Path) -> str:
    """The service a node belongs to: the first path component under ``docs/features/``."""
    try:
        rel = node.path.resolve().relative_to(features_root.resolve())
    except (ValueError, OSError):
        return ""
    return rel.parts[0] if rel.parts else ""


def _node_dict(node: UINode, resolver: LinkResolver, graph: Graph, features_root: Path) -> dict:
    edges = []
    for text, href in node.links:
        lt = resolver.resolve(node.path, href)
        if lt is None:  # a URL or a code ref (`path::symbol`), not a graph edge
            continue
        edges.append({"text": text, "href": href, "to": lt.node_id, "resolves": lt.resolved})
    return {
        "id": node.id,
        "type": node.type,
        "kind": node.kind,  # "file" | "section"
        "surface": _surface_of(node, features_root),
        "path": _rel(node.path, graph.root),
        "anchor": node.anchor,
        "title": node.title,
        "line": node.line,
        "level": node.level,  # heading depth
        "parent": node.parent,  # containment: id of the enclosing node
        "bullets": dict(node.meta),  # every `- key: value` under the node
        "edges": edges,  # resolved out-edges (parent:/extends:/on:/steps:/prose links)
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


def build(graph: Graph, *, etype: str | None = None, surface: str | None = None) -> dict:
    """Assemble the graph: every node (with bullets + out-edges) and a flat edge list.

    ``etype``/``surface`` optionally scope the dump to one node type or one service.
    """
    resolver = LinkResolver(graph)
    features_root = graph.doc_roots.get("features") or (graph.root / "docs" / "features")
    by_id = {n.id: n for n in graph.ui_nodes}
    nodes: list[dict] = []
    edges: list[dict] = []
    for n in graph.ui_nodes:
        if etype and n.type != etype:
            continue
        d = _node_dict(n, resolver, graph, features_root)
        if surface and d["surface"] != surface:
            continue
        d["title_path"], d["type_path"] = _paths(n.id, by_id)
        nodes.append(d)
        for e in d["edges"]:
            edges.append({"from": n.id, "to": e["to"], "text": e["text"],
                          "href": e["href"], "resolves": e["resolves"]})
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


# ── selectors ──────────────────────────────────────────────────────────────────────
# A query surface over build()'s output, so hierarchy questions ("timeout of the agent node")
# don't need jq. Selectors compose (AND); output is tree / ids / json.

def _seg_match(seg_type: str, seg_title: str, ntype: str, ntitle: str) -> bool:
    if seg_type and seg_type.lower() != (ntype or "").lower():
        return False
    return not (seg_title and seg_title.lower() not in (ntitle or "").lower())


def _parse_path(expr: str) -> tuple[list, list]:
    """`concept:agent / field:timeout` → ([(type,title), …], ['/', …]). Each segment is
    `type:title` (either side optional); `/` = descendant, `>` = direct child."""
    parts = re.split(r"\s*(/|>)\s*", expr.strip())
    segs: list = []
    ops: list = []
    for i, p in enumerate(parts):
        if i % 2:
            ops.append(p)
        else:
            t, sep, ti = p.partition(":")
            segs.append((t.strip(), ti.strip()) if sep else ("", p.strip()))
    return segs, ops


def _match_path(node: dict, segs: list, ops: list) -> bool:
    """The node's ancestor chain (type_path/title_path) matches the path, right-anchored on the
    node itself. `>` demands the immediately-preceding chain entry; `/` any earlier ancestor."""
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
    """Node-hops from *node* up to *target* (1 = direct child), or None if not an ancestor.
    Counts *nodes*, not heading levels — container/untyped headings don't consume a hop."""
    cur, depth, seen = node["parent"], 1, set()
    while cur and cur in by_id and cur not in seen:
        if cur == target:
            return depth
        seen.add(cur)
        cur = by_id[cur]["parent"]
        depth += 1
    return None


def select(data: dict, *, node_type: str | None = None, title: str | None = None,
           path: str | None = None, under: str | None = None, depth: int | None = None,
           has_bullet: str | None = None, bullet: str | None = None,
           links_to: str | None = None, orphans: bool = False) -> list:
    """Filter build()'s nodes by any combination of selectors (AND). Returns nodes in graph order."""
    nodes = data["nodes"]
    by_id = {n["id"]: n for n in nodes}
    incoming = {e["to"] for e in data["edges"] if e["to"]}
    segs = ops = None
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
        if orphans and n["id"] in incoming:
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
