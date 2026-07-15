"""Tests for select-story.py — within-epic story selection in dependency order (ostler model)."""
from __future__ import annotations

from conftest import init_repo, requires_ostler, run_script, write_epic, write_story

pytestmark = requires_ostler


def test_no_stories_listed(tmp_path):
    init_repo(tmp_path)
    (tmp_path / "docs" / "epics" / "e1").mkdir(parents=True)
    out = run_script("select-story.py", "docs/epics/e1", repo=tmp_path)
    assert out["has_story"] == "no"
    assert "no stories" in out["reason"]


def test_selects_unwritten_story(tmp_path):
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}, {"id": "i2"}], stories=[
        {"slug": "s1", "covers": ["i1"], "write": True},
        {"slug": "s2", "covers": ["i2"], "write": False},
    ])
    out = run_script("select-story.py", "docs/epics/e1", repo=tmp_path)
    assert out["has_story"] == "yes"
    assert out["story_slug"] == "s2"
    assert out["story_dir"] == "docs/epics/e1/stories/s2"


def test_all_written_returns_no(tmp_path):
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}], stories=[{"slug": "s1", "covers": ["i1"]}])
    out = run_script("select-story.py", "docs/epics/e1", repo=tmp_path)
    assert out["has_story"] == "no"


def test_dependency_order_respected(tmp_path):
    # s2 depends on s1; both unwritten → s1 selected first (topological order).
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}, {"id": "i2"}], stories=[
        {"slug": "s2", "deps": ["s1"], "covers": ["i2"], "write": False},
        {"slug": "s1", "covers": ["i1"], "write": False},
    ])
    out = run_script("select-story.py", "docs/epics/e1", repo=tmp_path)
    assert out["story_slug"] == "s1"


def test_placeholder_without_status_line_reselected(tmp_path):
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}], stories=[{"slug": "s1", "covers": ["i1"]}])
    # Overwrite the written story.md with a placeholder that has no `- **Status**:` line.
    write_story(tmp_path, "e1", "s1",
                body="---\ntype: story\nslug: s1\nstatus: not_started\n---\n# s1\n\n(placeholder)\n")
    out = run_script("select-story.py", "docs/epics/e1", repo=tmp_path)
    assert out["has_story"] == "yes"
    assert out["story_slug"] == "s1"
