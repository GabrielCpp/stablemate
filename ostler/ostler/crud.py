"""`ostler` mutation — create/delete epics, stories, features; add/remove seeds; set status.

All structural mutation goes through here so id allocation (``ids.py``) and the canonical markdown
layout (``SPEC.md`` / ``registry.py``) stay correct. Writers apply immediately and return a
:class:`Result`; the CLI prints its message.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import ids, markdown, registry
from .model import Graph


@dataclass
class Result:
    ok: bool
    message: str
    paths: list[Path] = field(default_factory=list)
    entity_id: str = ""   # the allocated id, for create commands (consumed via --json)


# ---------------------------------------------------------------------------
# markdown section helpers (operate on a MarkdownDoc's body, preserving frontmatter)
# ---------------------------------------------------------------------------
def _insert_subsection(doc: markdown.MarkdownDoc, heading: str, block: list[str]) -> None:
    """Insert a ``### …`` *block* under the ``## heading`` section, creating it if absent."""
    body_lines = doc.body.split("\n")
    sec = doc.find_section(heading)
    if sec is None:
        out = list(body_lines)
        while out and out[-1].strip() == "":
            out.pop()
        out += ["", f"## {heading}", "", *block]
        doc.body = "\n".join(out) + "\n"
    else:
        at = sec.line_end
        doc.body = "\n".join(body_lines[:at] + block + body_lines[at:])
    doc._sections = None


def _remove_subsection(doc: markdown.MarkdownDoc, heading: str, sub_title: str) -> bool:
    sec = doc.find_section(heading)
    if sec is None:
        return False
    for child in sec.children:
        if child.title.strip() == sub_title:
            body_lines = doc.body.split("\n")
            del body_lines[child.line_start:child.line_end]
            doc.body = "\n".join(body_lines)
            doc._sections = None
            return True
    return False


def _dump_frontmatter(fm: dict) -> str:
    return yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)


# ---------------------------------------------------------------------------
# epics
# ---------------------------------------------------------------------------
def create_epic(graph: Graph, name: str, title: str, prefix: str | None = None) -> Result:
    edir = graph.doc_roots["epics"] / name
    epic_md = edir / "epic.md"
    if epic_md.exists():
        return Result(False, f"epic '{name}' already exists")
    eid = ids.allocate(graph, prefix)
    fm = {"type": "epic", "id": eid, "title": title, "status": "planned"}
    text = f"---\n{_dump_frontmatter(fm)}---\n# Epic: {title}\n\n## Seeds\n\n## Stories\n"
    edir.mkdir(parents=True, exist_ok=True)
    epic_md.write_text(text, encoding="utf-8")
    return Result(True, f"created epic '{name}' ({eid})", [epic_md], entity_id=eid)


def delete_epic(graph: Graph, name: str) -> Result:
    edir = graph.doc_roots["epics"] / name
    if not (edir / "epic.md").exists():
        return Result(False, f"no epic '{name}'")
    import shutil
    shutil.rmtree(edir)
    todo = graph.doc_roots["epics"] / "index.md"
    removed = ""
    if todo.exists():
        from . import todo as todo_mod
        if todo_mod.prune(graph, name).ok:
            removed = " (removed from epics index)"
    return Result(True, f"deleted epic '{name}'{removed}", [edir])


# ---------------------------------------------------------------------------
# stories
# ---------------------------------------------------------------------------
def _story_block(slug: str, title: str, sid: str,
                 covers: list[str], depends: list[str]) -> list[str]:
    return [
        f"### {slug}",
        f"- title: {title}",
        f"- id: {sid}",
        f"- covers: {', '.join(covers) if covers else '(none)'}",
        f"- depends on: {', '.join(depends) if depends else '(none)'}",
        "",
    ]


def create_story(graph: Graph, epic_name: str, slug: str, title: str,
                 covers: list[str] | None = None, depends: list[str] | None = None,
                 prefix: str | None = None) -> Result:
    edir = graph.doc_roots["epics"] / epic_name
    epic_md = edir / "epic.md"
    if not epic_md.exists():
        return Result(False, f"no epic '{epic_name}'")
    story_md = edir / "stories" / slug / "story.md"
    if story_md.exists():
        return Result(False, f"story '{slug}' already exists")

    sid = ids.allocate(graph, prefix)
    doc = markdown.split(epic_md.read_text(encoding="utf-8"))
    _insert_subsection(doc, registry.STORIES_HEADING,
                       _story_block(slug, title, sid, covers or [], depends or []))
    epic_md.write_text(doc.render(), encoding="utf-8")

    fm = {"type": "story", "slug": slug, "status": "Not started"}
    body = (f"# Story: {title}\n\n## Context\n\n## Acceptance Criteria\n\n"
            f"## Implementation Status\n\n- **Status**: Not started\n")
    story_md.parent.mkdir(parents=True, exist_ok=True)
    story_md.write_text(f"---\n{_dump_frontmatter(fm)}---\n{body}", encoding="utf-8")
    return Result(True, f"created story '{slug}' ({sid}) in epic '{epic_name}'",
                  [epic_md, story_md], entity_id=sid)


def delete_story(graph: Graph, slug: str) -> Result:
    found = graph.find_story(slug)
    if found is None:
        return Result(False, f"no story '{slug}'")
    epic, story = found
    epic_md = epic.epic_md
    doc = markdown.split(epic_md.read_text(encoding="utf-8"))
    _remove_subsection(doc, registry.STORIES_HEADING, slug)
    epic_md.write_text(doc.render(), encoding="utf-8")
    if story.story_md and story.story_md.exists():
        import shutil
        shutil.rmtree(story.story_md.parent)
    return Result(True, f"deleted story '{slug}' from epic '{epic.name}'", [epic_md])


def set_status(graph: Graph, slug: str, status: str) -> Result:
    found = graph.find_story(slug)
    if found is None or found[1].story_md is None:
        return Result(False, f"no story '{slug}' with a story.md")
    path = found[1].story_md
    doc = markdown.split(path.read_text(encoding="utf-8"))
    fm = doc.frontmatter or {"type": "story", "slug": slug}
    fm["status"] = status
    doc.raw_frontmatter = _dump_frontmatter(fm)
    doc.body = re.sub(r"(\*\*Status\*\*:\s*).*", lambda m: m.group(1) + status,
                      doc.body, count=1)
    path.write_text(doc.render(), encoding="utf-8")
    return Result(True, f"status of '{slug}' → {status}", [path])


# ---------------------------------------------------------------------------
# seeds (live in epic.md `## Seeds`)
# ---------------------------------------------------------------------------
def add_seed(graph: Graph, epic_name: str, seed_id: str, status: str = registry.DEFAULT_SEED_STATUS,
             summary: str = "", meta: dict | None = None) -> Result:
    edir = graph.doc_roots["epics"] / epic_name
    epic_md = edir / "epic.md"
    if not epic_md.exists():
        return Result(False, f"no epic '{epic_name}'")
    if status not in registry.SEED_STATUSES:
        return Result(False, f"invalid status '{status}' (one of {', '.join(registry.SEED_STATUSES)})")
    doc = markdown.split(epic_md.read_text(encoding="utf-8"))
    sec = doc.find_section(registry.SEEDS_HEADING)
    if sec is not None and any(c.title.strip() == seed_id for c in sec.children):
        return Result(False, f"seed '{seed_id}' already exists in '{epic_name}'")
    block = [f"### {seed_id}", f"- status: {status}"]
    for key in ("surface", "legacySurface", "backing", "prerequisites", "sourceBullet"):
        val = (meta or {}).get(key)
        if val:
            block.append(f"- {key}: {val}")
    block.append("")
    if summary:
        block += [summary, ""]
    _insert_subsection(doc, registry.SEEDS_HEADING, block)
    epic_md.write_text(doc.render(), encoding="utf-8")
    return Result(True, f"added seed '{seed_id}' to epic '{epic_name}'", [epic_md])


def remove_seed(graph: Graph, epic_name: str, seed_id: str) -> Result:
    edir = graph.doc_roots["epics"] / epic_name
    epic_md = edir / "epic.md"
    if not epic_md.exists():
        return Result(False, f"no epic '{epic_name}'")
    doc = markdown.split(epic_md.read_text(encoding="utf-8"))
    if not _remove_subsection(doc, registry.SEEDS_HEADING, seed_id):
        return Result(False, f"no seed '{seed_id}' in '{epic_name}'")
    epic_md.write_text(doc.render(), encoding="utf-8")
    return Result(True, f"removed seed '{seed_id}' from epic '{epic_name}'", [epic_md])


# ---------------------------------------------------------------------------
# features
# ---------------------------------------------------------------------------
def create_feature(graph: Graph, slug: str, title: str, area: str = "",
                   route: str = "", prefix: str | None = None) -> Result:
    froot = graph.doc_roots["features"]
    path = (froot / area / f"{slug}.md") if area else (froot / f"{slug}.md")
    if path.exists():
        return Result(False, f"feature '{slug}' already exists")
    fid = ids.allocate(graph, prefix)
    fm = {"type": "feature", "id": fid, "slug": slug, "title": title}
    if area:
        fm["area"] = area
    if route:
        fm["route"] = route
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{_dump_frontmatter(fm)}---\n# {title}\n\n", encoding="utf-8")
    return Result(True, f"created feature '{slug}' ({fid})", [path], entity_id=fid)


def delete_feature(graph: Graph, slug: str) -> Result:
    for feat in graph.features:
        if feat.slug == slug:
            feat.path.unlink()
            return Result(True, f"deleted feature '{slug}'", [feat.path])
    return Result(False, f"no feature '{slug}'")
