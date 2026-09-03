"""`ostler list` / `search` / `query` — retrieval over the typed knowledge graph.

Returns plain dicts/lists (JSON-friendly). ``list`` enumerates Concepts of a type with filters,
``search`` does full-text over titles/bodies, ``query`` answers the reverse-index questions the
workflows ask (stories-covering-seed, surfaces-referenced-by-story).
"""

from __future__ import annotations

from pathlib import Path

from ostler import crud_generic, provenance, registry
from ostler.model import Graph, UINode


def _story_row(graph: Graph, epic, story) -> dict:
    return {
        "type": "story", "id": story.eid, "externalKey": story.external_key,
        "aliases": list(story.aliases), "slug": story.slug, "epic": epic.name,
        "title": story.title, "status": story.status, "covers": story.seed_items,
        "dependsOn": story.dependencies,
        "path": story.path,
        # Whether the story says anything, and which required sections are still blank —
        # so a caller never has to open story.md and decide for itself what "written" means.
        # `hasStoryMd` separates the two ways a story can be unauthored: no file at all, or a
        # file that is still the scaffold. They need different words in a report.
        "authored": story.authored, "unwrittenSections": list(story.unwritten_sections),
        "hasStoryMd": story.story_md is not None,
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
            "prerequisites": raw.get("prerequisites", ""),
            "design": raw.get("design", "")}


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
    elif etype == "feature":
        for f in graph.features:
            rows.append({"type": "feature", "slug": f.slug, "area": f.area, "title": f.title,
                         "route": f.data.get("route", ""),
                         "path": f.path.relative_to(graph.root).as_posix()})
    elif etype in registry.UI_TYPES_BY_NAME:
        rows = [_ui_row(graph, n) for n in graph.ui_nodes_of_type(etype)]
    else:
        rows = crud_generic.find_instance(graph, etype)

    if epic is not None:
        # By directory name or by bare slug: epic directories are numbered, and a caller
        # filtering `epic="checkout-flow"` means `0001-checkout-flow`.
        want = registry.epic_slug(epic)
        rows = [r for r in rows
                if registry.epic_slug(str(r.get("epic") or r.get("name") or "")) == want]
    if status is not None:
        rows = [r for r in rows if str(r.get("status", "")).lower() == status.lower()]
    return rows


def _body_text(path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def search(graph: Graph, q: str, etype: str | None = None) -> list[dict]:
    ql = q.lower()
    hits: list[dict] = []
    types = [etype] if etype else (
        ["epic", "milestone", "story", "seed", "feature", *registry.UI_TYPES_BY_NAME])
    for t in types:
        for row in list_entities(graph, t):
            hay = " ".join(str(v) for v in row.values()).lower()
            if t in ("milestone", "story", "feature") or t in registry.UI_TYPES_BY_NAME:
                path = None
                if t == "milestone":
                    path = next((m.path for m in graph.milestones if m.name == row["name"]), None)
                elif t == "story":
                    found = graph.find_story(row["slug"])
                    path = found[1].story_md if found else None
                elif t == "feature":
                    path = next((f.path for f in graph.features if f.slug == row["slug"]), None)
                else:  # UI node — resolve by identity
                    node = graph.find_ui_node(row["id"])
                    path = node.path if node else None
                if path:
                    hay += " " + _body_text(path).lower()
            if ql in hay:
                hits.append(row)
    return hits


def query(
    graph: Graph,
    name: str,
    arg: str,
    checkouts: dict[str, Path] | None = None,
) -> list[dict]:
    source_checkouts = checkouts or {}
    if name == "story-provenance":
        return provenance.story_provenance(graph, arg, source_checkouts)
    if name == "commit-story":
        return provenance.commit_story(graph, arg, source_checkouts)
    if name == "node-provenance":
        return provenance.node_provenance(graph, arg, source_checkouts)
    if name == "story-for-node":
        return provenance.story_for_node(graph, arg, source_checkouts)
    if name == "stories-covering-seed":
        return [_story_row(graph, e, s) for e in graph.epics for s in e.stories
                if arg in s.seed_items]
    if name == "surfaces-referenced-by-story":
        found = graph.find_story(arg)
        if not found:
            return []
        return _surfaces_referenced(graph, found[1])
    return []


def _surfaces_referenced(graph: Graph, story) -> list[dict]:
    """Every surface a story points at through OKF book nodes.

    The book is the current channel — a story grounds itself by citing the ids of the
    surface/component/interaction/flow nodes it works on, and a UI node's id is a
    repo-relative path, so the citation is an ordinary markdown link. Rows are tagged with
    ``kind`` so a caller can tell a resolved citation from one that points at nothing:
    ``ui`` resolved to a node in the graph, ``file`` resolved to a document on disk that is
    not a UI node (a feature doc, a sibling story), ``missing`` resolved to nothing at all.
    A dangling citation is reported rather than dropped — silently omitting it would make a
    typo'd node id indistinguishable from a story that never cited one.

    An anchor **into a document that is itself a book node** is held to the same standard as
    the path: ``settings.md#save-prophile`` names no section node, so it is ``missing`` rather
    than ``file``. The file existing is not evidence the cited section does, and that is the
    likelier typo of the two. An anchor into any other document stays ``file`` — ordinary
    markdown deep-links into a spec or a sibling story are not node citations to begin with.
    """
    rows: list[dict] = []
    seen: set[str] = set()
    for href in story.doc_refs:
        ident = graph.resolve_doc_ref(href, origin=story.story_md)
        if not ident or ident in seen:
            continue
        seen.add(ident)
        node = graph.find_ui_node(ident)
        path_part, _, anchor = ident.partition("#")
        if node:
            rows.append({"path": ident, "kind": "ui", "type": node.type, "title": node.title})
        elif anchor and graph.find_ui_node(path_part):
            rows.append({"path": ident, "kind": "missing"})
        elif (graph.root / path_part).is_file():
            rows.append({"path": ident, "kind": "file"})
        else:
            rows.append({"path": ident, "kind": "missing"})
    return rows


QUERIES = (
    "stories-covering-seed",
    "surfaces-referenced-by-story",
    *provenance.PROVENANCE_QUERIES,
)
