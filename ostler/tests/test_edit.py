from __future__ import annotations

from pathlib import Path

from ostler import doctor, edit, markdown
from ostler.model import load

from conftest import knowledge_md, write


def _gap_owner(path: Path, gap_id: str) -> str:
    fm = markdown.split(path.read_text()).frontmatter or {}
    return next(g["owner"] for g in fm["gaps"] if g["id"] == gap_id)


def test_set_owner_on_markdown(repo: Path):
    rec_path = repo / "docs/knowledge/area/rec.md"
    write(rec_path, knowledge_md("area/rec", [("gap-x", "")]))  # empty owner

    plan = edit.set_owner(load(repo), "gap-x", "01-foo")
    assert len(plan.changes) == 1
    plan.apply()

    assert _gap_owner(rec_path, "gap-x") == "01-foo"
    # frontmatter still parses and the body is intact
    doc = markdown.split(rec_path.read_text())
    assert doc.frontmatter["surface"] == "area/rec"
    assert "body text" in doc.body


def test_rename_cascades_and_stays_clean(repo: Path):
    graph = load(repo)
    plan = edit.rename(graph, "01-foo", "01-foofoo")
    assert plan.changes  # epic.md + story.md + rec.md
    assert plan.moves    # story folder move
    plan.apply()

    # the story folder moved
    assert (repo / "docs/epics/epic-a/stories/01-foofoo/story.md").exists()
    assert not (repo / "docs/epics/epic-a/stories/01-foo").exists()

    # gap owner that pointed at 01-foo followed the rename
    assert _gap_owner(repo / "docs/knowledge/area/rec.md", "gap-x") == "01-foofoo"

    # and the graph is still clean
    report = doctor.run(load(repo))
    assert report.errors == 0, [f.message for f in report.findings if f.severity == "error"]


def test_rename_does_not_touch_unrelated_substrings(repo: Path):
    # 'foo' must not be mangled when renaming the full slug '01-foo'.
    story = repo / "docs/epics/epic-a/stories/01-foo/story.md"
    story.write_text(story.read_text() + "\nThe word foobar stays.\n", encoding="utf-8")
    plan = edit.rename(load(repo), "01-foo", "01-baz")
    plan.apply()
    moved = (repo / "docs/epics/epic-a/stories/01-baz/story.md").read_text()
    assert "foobar stays" in moved


def test_relink_replaces_path_everywhere(repo: Path):
    plan = edit.relink(load(repo), "docs/knowledge/area/rec.md",
                       "docs/knowledge/area/renamed.md")
    assert plan.changes
    plan.apply()
    story = (repo / "docs/epics/epic-a/stories/01-foo/story.md").read_text()
    assert "renamed.md" in story
    assert "rec.md" not in story


def test_edit_dry_run_writes_nothing(repo: Path):
    rec_path = repo / "docs/knowledge/area/rec.md"
    before = rec_path.read_text()
    edit.set_owner(load(repo), "gap-x", "01-bar")  # build plan, do not apply
    assert rec_path.read_text() == before


def test_set_owner_unknown_gap_errors(repo: Path):
    plan = edit.set_owner(load(repo), "nope", "01-foo")
    assert plan.error
