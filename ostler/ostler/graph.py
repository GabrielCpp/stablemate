"""``ostler graph`` — dump the whole OKF graph (nodes + edges + bullets) as JSON to filter on.

``list``/``search`` are per-type / full-text and ``trace`` walks out from one node; this emits
*every* UI node together with its parsed ``- key: value`` bullets and its resolved out-edges, plus a
flat edge list. That lets an agent (or ``jq``) filter the graph structurally rather than by prose
match — e.g. the node whose ``code:`` is a given symbol (dedup before enqueue), every
``code:``/``verify:`` bullet (inventory coverage), or the nodes nothing links to (orphans).
"""
from __future__ import annotations

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
        "bullets": dict(node.meta),  # every `- key: value` under the node
        "edges": edges,  # resolved out-edges (parent:/extends:/on:/steps:/prose links)
    }


def build(graph: Graph, *, etype: str | None = None, surface: str | None = None) -> dict:
    """Assemble the graph: every node (with bullets + out-edges) and a flat edge list.

    ``etype``/``surface`` optionally scope the dump to one node type or one service.
    """
    resolver = LinkResolver(graph)
    features_root = graph.doc_roots.get("features") or (graph.root / "docs" / "features")
    nodes: list[dict] = []
    edges: list[dict] = []
    for n in graph.ui_nodes:
        if etype and n.type != etype:
            continue
        d = _node_dict(n, resolver, graph, features_root)
        if surface and d["surface"] != surface:
            continue
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
