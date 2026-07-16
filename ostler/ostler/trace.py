"""`ostler trace` — walk the organization graph from any node (seed id, story slug,
surface or doc path) and print the chain of references and their statuses."""

from __future__ import annotations

from . import links as links_mod
from .model import Graph, UINode


def _find_ui(graph: Graph, token: str) -> UINode | None:
    """Resolve *token* to a UI node: exact identity (path / path#anchor), then section anchor,
    then a file node's slug or filename stem."""
    node = graph.find_ui_node(token)
    if node is not None:
        return node
    for n in graph.ui_nodes:
        if n.kind == "section" and n.anchor == token:
            return n
    for n in graph.ui_nodes:
        if n.kind == "file" and (str(n.data.get("slug") or "") == token or n.path.stem == token):
            return n
    return None


def _trace_ui(graph: Graph, token: str) -> list[str] | None:
    node = _find_ui(graph, token)
    if node is None:
        return None
    resolver = links_mod.LinkResolver(graph)
    rel = node.path.relative_to(graph.root).as_posix()
    out = [f"{node.type}  {node.id}",
           f"  title: {node.title or '—'}",
           f"  file:  {rel}:{node.line}"]

    # outbound edges — every doc link in the node's region, with resolution status
    for _text, href in node.links:
        target = resolver.resolve(node.path, href)
        if target is None:
            continue
        if not target.file_exists:
            status = "DANGLING (no such file)"
        elif target.anchor and not target.anchor_exists:
            status = "MISSING ANCHOR"
        else:
            status = "ok"
        out.append(f"  → {target.node_id}  [{status}]")

    # inbound edges — other UI nodes whose links resolve to this node
    for other in graph.ui_nodes:
        if other is node:
            continue
        for _text, href in other.links:
            target = resolver.resolve(other.path, href)
            if target is not None and target.node_id == node.id:
                out.append(f"  ← referenced by  {other.type}  {other.id}")
                break
    return out


def run(graph: Graph, token: str) -> tuple[list[str], bool]:
    """Return (lines, found)."""
    out: list[str] = []

    # 1) story slug
    hit = graph.find_story(token)
    if hit:
        epic, story = hit
        out.append(f"story  {story.slug}   (epic: {epic.name})")
        out.append(f"  title:  {story.title}")
        out.append(f"  status: {story.status or '—'}")
        out.append(f"  file:   {story.story_md if story.story_md else '(missing)'}")
        if story.dependencies:
            out.append(f"  depends on: {', '.join(story.dependencies)}")
        for sid in story.seed_items:
            seed = next((s for s in epic.seeds if s.id == sid), None)
            label = seed.summary if seed else "(unknown seed)"
            out.append(f"  seed  {sid}: {label}")
        return out, True

    # 2) seed id
    epic = graph.epic_of_seed(token)
    if epic:
        seed = next(s for s in epic.seeds if s.id == token)
        out.append(f"seed   {seed.id}   (epic: {epic.name}, status: {seed.status or '—'})")
        out.append(f"  {seed.summary}")
        covering = [s for s in epic.stories if token in s.seed_items]
        if covering:
            for s in covering:
                out.append(f"  covered by story  {s.slug}  ({s.status or '—'})")
        else:
            out.append("  covered by: NOTHING (orphan)" if seed.active else "  covered by: — (inactive)")
        return out, True

    # 3) surface
    rec = next((r for r in graph.knowledge if r.surface == token), None)
    if rec:
        out.append(f"surface {rec.surface}   ({rec.fmt}: {rec.path})")
        return out, True

    # 4) path
    referrers = [s.slug for e in graph.epics for s in e.stories if token in s.knowledge_refs]
    if referrers:
        out.append(f"path   {token}")
        for slug in referrers:
            out.append(f"  referenced by story  {slug}")
        return out, True

    # 5) UI-profile node (screen/component/interaction/… — walks resolved path links)
    ui = _trace_ui(graph, token)
    if ui is not None:
        return ui, True

    return [f"no node found for '{token}'"], False
