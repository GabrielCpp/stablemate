"""Shared fixtures + builders: a minimal on-disk org tree in the new markdown Concept format."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, data: dict) -> None:
    """Only ``.agents/ids.json`` remains JSON in this format."""
    write(path, json.dumps(data, indent=2) + "\n")


def epic_md(eid: str, title: str, seeds: list[tuple[str, str, str]],
            stories: list[tuple[str, str, list[str], list[str]]]) -> str:
    """seeds: (id, status, summary). stories: (slug, title, covers[], depends[])."""
    out = ["---", "type: epic", f"id: {eid}", f"title: {title}", "---",
           f"# Epic: {title}", ""]
    if seeds:
        out += ["## Seeds", ""]
        for sid, status, summary in seeds:
            out += [f"### {sid}", f"- status: {status}", "", summary, ""]
    out += ["## Stories", ""]
    for slug, stitle, covers, depends in stories:
        out += [f"### {slug}",
                f"- title: {stitle}",
                f"- covers: {', '.join(covers) if covers else '(none)'}",
                f"- depends on: {', '.join(depends) if depends else '(none)'}",
                ""]
    return "\n".join(out) + "\n"


def story_md(slug: str, title: str, status: str,
             gap: str | None = None, knowledge_ref: str | None = None) -> str:
    body = ["---", "type: story", f"slug: {slug}", f"status: {status}", "---",
            f"# Story: {title}", "", "## Implementation Status", "",
            f"- **Status**: {status}", "", "## Acceptance Criteria", ""]
    line = "- The thing works."
    if gap:
        line += f" [gap: {gap}]"
    body.append(line)
    if knowledge_ref:
        body += ["", f"Knowledge record: `{knowledge_ref}`."]
    return "\n".join(body) + "\n"


def knowledge_md(surface: str, gaps: list[tuple[str, str]] | None = None, route: str = "") -> str:
    """gaps: (id, owner) tuples (disposition scoped)."""
    out = ["---", "type: knowledge", f"surface: {surface}"]
    if route:
        out.append(f"route: {route}")
    out.append("gaps:")
    for gid, owner in (gaps or []):
        out += [f"- id: {gid}", f"  owner: {owner}", "  disposition: scoped"]
    if not gaps:
        out[-1] = "gaps: []"
    out += ["---", f"# {surface}", "", "body text", ""]
    return "\n".join(out) + "\n"


def feature_md(slug: str, title: str, area: str = "", route: str = "") -> str:
    out = ["---", "type: feature", f"slug: {slug}", f"title: {title}"]
    if area:
        out.append(f"area: {area}")
    if route:
        out.append(f"route: {route}")
    out += ["---", f"# {title}", "", "feature prose", ""]
    return "\n".join(out) + "\n"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A clean two-epic repo with two markdown knowledge records."""
    root = tmp_path

    # epic-a: story 01-foo covers seed-a1; seed-a2 is resolved (inactive).
    write(root / "docs/epics/epic-a/epic.md", epic_md(
        "t-1", "epic-a",
        seeds=[("seed-a1", "researched", "first"), ("seed-a2", "resolved", "done")],
        stories=[("01-foo", "Foo", ["seed-a1"], [])],
    ))
    write(root / "docs/epics/epic-a/stories/01-foo/story.md",
          story_md("01-foo", "Foo", "Not started", "gap-x", "docs/knowledge/area/rec.md"))

    # epic-b: story 01-bar covers seed-b1.
    write(root / "docs/epics/epic-b/epic.md", epic_md(
        "t-2", "epic-b",
        seeds=[("seed-b1", "researched", "bee")],
        stories=[("01-bar", "Bar", ["seed-b1"], [])],
    ))
    write(root / "docs/epics/epic-b/stories/01-bar/story.md",
          story_md("01-bar", "Bar", "Not started"))

    # knowledge: rec (gap-x owned by 01-foo) + rec2 (gap-y owned by 01-bar)
    write(root / "docs/knowledge/area/rec.md", knowledge_md("area/rec", [("gap-x", "01-foo")]))
    write(root / "docs/knowledge/area/rec2.md", knowledge_md("area/rec2", [("gap-y", "01-bar")]))

    return root
