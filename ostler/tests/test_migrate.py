"""The migration is lossless: an old-format repo folds into the new format with the same typed
graph, conformant under doctor, and no legacy JSON left behind."""
from __future__ import annotations

import json
from pathlib import Path

from ostler import doctor, todo
from ostler.model import load
from ostler.scripts import okf_migrate

from conftest import write


def _old_repo(root: Path) -> None:
    write(root / "docs/epics/epic-a/seed.json", json.dumps({
        "epic": "epic-a",
        "items": [
            {"id": "seed-a1", "status": "researched", "summary": "first", "backing": "GET /x"},
            {"id": "seed-a2", "status": "resolved", "summary": "done"},
        ],
    }))
    write(root / "docs/epics/epic-a/dependencies.json", json.dumps({
        "epicName": "epic-a", "epicTitle": "Epic A", "epicId": "item-1",
        "stories": [{"slug": "01-foo", "title": "Foo", "id": "item-2", "phase": 1,
                     "seedItems": ["seed-a1"], "dependencies": []}],
    }))
    write(root / "docs/epics/epic-a/epic.md", "# Epic A\n\n## Goal\n\nbuild it\n")
    write(root / "docs/epics/epic-a/stories/01-foo/story.md",
          "# Story: Foo\n\n## Implementation Status\n\n- **Status**: Not started\n\n"
          "## Acceptance Criteria\n\n- works [gap: gap-x]\n\nSee `docs/knowledge/area/rec.json`.\n")
    write(root / "docs/knowledge/area/rec.json", json.dumps({
        "surface": "area/rec", "gaps": [{"id": "gap-x", "owner": "01-foo", "disposition": "scoped"}],
    }))
    write(root / "docs/features/inventory.json", json.dumps({
        "surfaces": [{"area": "area", "slug": "rec", "title": "Rec", "route": "/rec"}],
    }))
    write(root / "docs/epics/epics-todo.json", json.dumps(["epic-a"]))


def test_migration_is_lossless(tmp_path: Path):
    _old_repo(tmp_path)
    rep = okf_migrate.migrate(tmp_path)
    assert rep["epics"] == 1 and rep["stories"] == 1 and rep["todo"]

    g = load(tmp_path)
    epic = next(e for e in g.epics if e.name == "epic-a")
    assert epic.eid == "item-1" and epic.title == "Epic A"
    assert {s.id: s.status for s in epic.seeds} == {"seed-a1": "researched", "seed-a2": "resolved"}
    story = epic.stories[0]
    assert story.slug == "01-foo" and story.seed_items == ["seed-a1"] and story.title == "Foo"

    # narrative preserved, canonical sections added
    epic_text = (tmp_path / "docs/epics/epic-a/epic.md").read_text()
    assert "build it" in epic_text and "## Seeds" in epic_text and "## Stories" in epic_text

    # knowledge converted; story ref followed .json → .md
    assert (tmp_path / "docs/knowledge/area/rec.md").exists()
    story_text = (tmp_path / "docs/epics/epic-a/stories/01-foo/story.md").read_text()
    assert "rec.md" in story_text and "rec.json" not in story_text

    # feature concept from inventory; queue index
    assert (tmp_path / "docs/features/area/rec.md").exists()
    assert todo.list_epics(load(tmp_path)) == ["epic-a"]

    # conformant + no legacy JSON
    report = doctor.run(g)
    assert report.errors == 0, [f.message for f in report.findings if f.severity == "error"]
    leftovers = list(tmp_path.rglob("seed.json")) + list(tmp_path.rglob("dependencies.json")) \
        + list(tmp_path.rglob("epics-todo.json")) + list(tmp_path.rglob("inventory.json")) \
        + list((tmp_path / "docs/knowledge").rglob("*.json"))
    assert leftovers == []


def test_migration_idempotent(tmp_path: Path):
    _old_repo(tmp_path)
    okf_migrate.migrate(tmp_path)
    before = {p: p.read_text() for p in (tmp_path / "docs").rglob("*.md")}
    rep2 = okf_migrate.migrate(tmp_path)
    assert rep2["epics"] == 0 and rep2["stories"] == 0 and not rep2["todo"]
    after = {p: p.read_text() for p in (tmp_path / "docs").rglob("*.md")}
    assert before == after
