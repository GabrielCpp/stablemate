"""`ostler list` / `search` / `query` — retrieval over the typed knowledge graph."""

from __future__ import annotations

from ostler import crud_generic, textindex
from ostler.model import Graph


def _story_row(graph: Graph, epic, story) -> dict:
    return {
        "type": "story", "id": story.eid,
        "aliases": list(story.aliases), "slug": story.slug, "epic": epic.name,
        "title": story.title, "status": story.status, "covers": story.seed_items,
        "dependsOn": story.dependencies, "services": list(story.services),
        "path": story.path,
        "authored": story.authored, "unwrittenSections": list(story.unwritten_sections),
        "hasStoryMd": story.story_md is not None,
    }


def _seed_row(epic, seed) -> dict:
    raw = seed.raw or {}
    return {"type": "seed", "id": seed.id, "epic": epic.name, "status": seed.status,
            "active": seed.active, "summary": seed.summary,
            "surface": raw.get("surface", ""),
            "legacySurface": raw.get("legacysurface", ""),
            "currentState": raw.get("currentstate", ""),
            "sourceRecord": raw.get("sourcerecord", ""),
            "backing": raw.get("backing", ""),
            "prerequisites": raw.get("prerequisites", ""),
            "design": raw.get("design", ""),
            "services": list(seed.services)}


def list_entities(graph: Graph, etype: str, epic: str | None = None,
                  status: str | None = None) -> list[dict]:
    rows: list[dict] = []
    if etype == "epic":
        for e in graph.epics:
            rows.append({"type": "epic", "name": e.name, "id": e.eid, "title": e.title,
                         "status": e.status, "seeds": len(e.seeds), "stories": len(e.stories)})
    elif etype == "milestone":
        for m in graph.milestones:
            rows.append({"type": "milestone", "name": m.name, "id": m.eid, "title": m.title,
                          "status": m.status, "dependsOn": m.depends_on, "epics": m.epics,
                          "sourceItems": m.source_items,
                          "path": m.path.relative_to(graph.root).as_posix()})
    elif etype == "story":
        for e in graph.epics:
            for s in e.stories:
                rows.append(_story_row(graph, e, s))
    elif etype == "seed":
        for e in graph.epics:
            for s in e.seeds:
                rows.append(_seed_row(e, s))
    else:
        rows = crud_generic.find_instance(graph, etype)

    if epic is not None:
        found = graph.epic_by_ref(epic)
        want = found.name if found is not None else epic
        rows = [r for r in rows if str(r.get("epic") or r.get("name") or "") == want]
    if status is not None:
        rows = [r for r in rows if str(r.get("status", "")).lower() == status.lower()]
    return rows


def search(graph: Graph, q: str, etype: str | None = None, **kw) -> list[dict]:
    return textindex.search(graph, q, etype=etype, **kw)


def query(graph: Graph, name: str, arg: str) -> list[dict]:
    if name == "stories-covering-seed":
        return [_story_row(graph, e, s) for e in graph.epics for s in e.stories
                if arg in s.seed_items]
    return []


QUERIES = ("stories-covering-seed",)
