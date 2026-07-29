"""Tests for select-story.py — within-epic story selection in dependency order (ostler model)."""
from __future__ import annotations

from conftest import (
    init_repo,
    run_script,
    scaffold_story_body,
    write_epic,
    write_story,
)


def test_epic_dir_without_epic_md(tmp_path):
    # A bare directory is not an epic — ostler cannot load it, so it has no stories to write
    # and the node must not read that as "everything is authored".
    init_repo(tmp_path)
    (tmp_path / "docs" / "epics" / "e1").mkdir(parents=True)
    out = run_script("select-story.py", "docs/epics/e1", repo=tmp_path)
    assert out["has_story"] == "no"
    assert "e1" in out["reason"]


def test_no_stories_listed(tmp_path):
    # epic.md exists but its `## Stories` is empty: nothing to author *yet*, which is a
    # different fact from "all authored" — the reason text has to say so.
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}], stories=[])
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


def test_bare_scaffold_reselected(tmp_path):
    """THE regression: `ostler create story`'s own scaffold must not read as authored.

    It carries a `- **Status**:` line and all three headings, which is what the old
    presence-based selector took as proof of authoring — so every story was born done, the loop
    routed past `write_story` entirely, and a run produced 44 empty stories and reported success.
    """
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}], stories=[{"slug": "s1", "covers": ["i1"]}])
    write_story(tmp_path, "e1", "s1", body=scaffold_story_body("s1"))
    out = run_script("select-story.py", "docs/epics/e1", repo=tmp_path)
    assert out["has_story"] == "yes"
    assert out["story_slug"] == "s1"


def test_placeholder_without_status_line_reselected(tmp_path):
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}], stories=[{"slug": "s1", "covers": ["i1"]}])
    # Overwrite the written story.md with a placeholder that has no `- **Status**:` line.
    write_story(tmp_path, "e1", "s1",
                body="---\ntype: story\nslug: s1\nstatus: not_started\n---\n# s1\n\n(placeholder)\n")
    out = run_script("select-story.py", "docs/epics/e1", repo=tmp_path)
    assert out["has_story"] == "yes"
    assert out["story_slug"] == "s1"


def test_progress_counts_only_authored(tmp_path):
    # Two authored, one scaffold, one missing → "2/4" and the first unauthored in DAG order.
    write_epic(tmp_path, "e1",
               seeds=[{"id": f"i{i}"} for i in range(1, 5)],
               stories=[{"slug": "s1", "covers": ["i1"]},
                        {"slug": "s2", "covers": ["i2"]},
                        {"slug": "s3", "covers": ["i3"]},
                        {"slug": "s4", "covers": ["i4"], "write": False}])
    write_story(tmp_path, "e1", "s3", body=scaffold_story_body("s3"))
    out = run_script("select-story.py", "docs/epics/e1", repo=tmp_path)
    assert out["has_story"] == "yes"
    assert out["story_slug"] == "s3"
    assert out["progress"] == "2/4"
    assert out["remaining_count"] == "2"
