"""`ostler list` / `search` / `query` — retrieval over the typed knowledge graph.

Returns plain dicts/lists (JSON-friendly). ``list`` enumerates Concepts of a type with filters,
``search`` does full-text over titles/bodies, ``query`` answers the reverse-index questions the
workflows ask (gaps-in-story, stories-covering-seed, surfaces-referenced-by-story).
"""

from __future__ import annotations

from . import crud_generic, registry
from .model import Graph, UINode


def _story_row(graph: Graph, epic, story) -> dict:
    return {
        "type": "story", "slug": story.slug, "epic": epic.name, "title": story.title,
        "status": story.status, "covers": story.seed_items, "dependsOn": story.dependencies,
        "path": story.path,
    }


def _ui_row(graph: Graph, node: UINode) -> dict:
    """A UI node as a JSON row. Section nodes carry ``anchor``; the ``id`` is ``path#anchor``
    (file nodes: the repo-relative path) so the agent-fix loop can address either directly."""
    row = {"type": node.type, "kind": node.kind, "id": node.id, "title": node.title,
           "path": node.path.relative_to(graph.root).as_posix(), "line": node.line}
    if node.kind == "section":
        row["anchor"] = node.anchor
    return row


def _seed_row(epic, seed) -> dict:
    # `seed.raw` carries the epic.md `### <id>` metadata bullets with lowercased keys
    # (`legacySurface:` → "legacysurface", etc.); surface them so the workflow's grounding
    # / prune gates can read the same fields the old seed.json exposed.
    raw = seed.raw or {}
    return {"type": "seed", "id": seed.id, "epic": epic.name, "status": seed.status,
            "active": seed.active, "summary": seed.summary,
            "surface": raw.get("surface", ""),
            "legacySurface": raw.get("legacysurface", ""),
            "currentState": raw.get("currentstate", ""),
            "sourceBullet": raw.get("sourcebullet", ""),
            "backing": raw.get("backing", ""),
            "prerequisites": raw.get("prerequisites", "")}


def list_entities(graph: Graph, etype: str, epic: str | None = None,
                  status: str | None = None) -> list[dict]:
    rows: list[dict] = []
    if etype == "epic":
        for e in graph.epics:
            rows.append({"type": "epic", "name": e.name, "id": e.eid, "title": e.title,
                         "status": e.status, "seeds": len(e.seeds), "stories": len(e.stories)})
    elif etype == "story":
        for e in graph.epics:
            for s in e.stories:
                rows.append(_story_row(graph, e, s))
    elif etype == "seed":
        for e in graph.epics:
            for s in e.seeds:
                rows.append(_seed_row(e, s))
    elif etype == "knowledge":
        for r in graph.knowledge:
            rows.append({"type": "knowledge", "surface": r.surface,
                         "route": str(r.data.get("route", "")),
                         "path": r.path.relative_to(graph.root).as_posix(),
                         "gaps": [g.id for g in r.gaps]})
    elif etype == "feature":
        for f in graph.features:
            rows.append({"type": "feature", "slug": f.slug, "area": f.area, "title": f.title,
                         "route": f.data.get("route", ""),
                         "path": f.path.relative_to(graph.root).as_posix()})
    elif etype == "gap":
        for r in graph.knowledge:
            for g in r.gaps:
                rows.append({"type": "gap", "id": g.id, "surface": r.surface,
                             "owner": g.owner, "disposition": g.disposition})
    elif etype in registry.UI_TYPES_BY_NAME:
        rows = [_ui_row(graph, n) for n in graph.ui_nodes_of_type(etype)]
    else:
        rows = crud_generic.find_instance(graph, etype)

    if epic is not None:
        rows = [r for r in rows if r.get("epic") == epic or r.get("name") == epic]
    if status is not None:
        rows = [r for r in rows if str(r.get("status", "")).lower() == status.lower()]
    return rows


def _body_text(path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def search(graph: Graph, q: str, etype: str | None = None,
           owner: str | None = None, tag: str | None = None) -> list[dict]:
    ql = q.lower()
    hits: list[dict] = []
    types = [etype] if etype else (
        ["epic", "story", "seed", "knowledge", "feature", "gap", *registry.UI_TYPES_BY_NAME])
    for t in types:
        for row in list_entities(graph, t):
            hay = " ".join(str(v) for v in row.values()).lower()
            if t in ("story", "knowledge", "feature") or t in registry.UI_TYPES_BY_NAME:
                path = None
                if t == "story":
                    found = graph.find_story(row["slug"])
                    path = found[1].story_md if found else None
                elif t == "knowledge":
                    path = next((r.path for r in graph.knowledge if r.surface == row["surface"]), None)
                elif t == "feature":
                    path = next((f.path for f in graph.features if f.slug == row["slug"]), None)
                else:  # UI node — resolve by identity
                    node = graph.find_ui_node(row["id"])
                    path = node.path if node else None
                if path:
                    hay += " " + _body_text(path).lower()
            if owner and row.get("owner") != owner:
                continue
            if tag and t == "gap" and row.get("id") != tag:
                continue
            if ql in hay:
                hits.append(row)
    return hits


def query(graph: Graph, name: str, arg: str) -> list[dict]:
    if name == "gaps-in-story":
        owned = [{"id": g.id, "surface": r.surface, "via": "owner"}
                 for r in graph.knowledge for g in r.gaps if g.owner == arg]
        found = graph.find_story(arg)
        tagged = []
        if found:
            tags = set(found[1].gap_tags)
            tagged = [{"id": g.id, "surface": r.surface, "via": "tag"}
                      for r in graph.knowledge for g in r.gaps if g.id in tags]
        seen, out = set(), []
        for row in owned + tagged:
            if row["id"] not in seen:
                seen.add(row["id"])
                out.append(row)
        return out
    if name == "stories-covering-seed":
        return [_story_row(graph, e, s) for e in graph.epics for s in e.stories
                if arg in s.seed_items]
    if name == "surfaces-referenced-by-story":
        found = graph.find_story(arg)
        if not found:
            return []
        return [{"path": ref} for ref in found[1].knowledge_refs]
    return []


QUERIES = ("gaps-in-story", "stories-covering-seed", "surfaces-referenced-by-story")
