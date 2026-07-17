"""Tests for validate-artifacts.py — final coder-consumability gate (ostler model)."""
from __future__ import annotations

from conftest import init_repo, requires_ostler, run_script, write_epic

pytestmark = requires_ostler


def test_good_tree_passes(tmp_path):
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}], stories=[{"slug": "s1", "covers": ["i1"]}])
    out = run_script("validate-artifacts.py", "docs/epics", repo=tmp_path)
    assert out["artifacts_ok"] == "yes", out["artifacts_errors"]


def test_empty_index_fails(tmp_path):
    init_repo(tmp_path)  # root marker, but the epics index lists no epics
    out = run_script("validate-artifacts.py", "docs/epics", repo=tmp_path)
    assert out["artifacts_ok"] == "no"
    assert "index lists no epics" in out["artifacts_errors"]


def test_epic_with_no_stories_fails(tmp_path):
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}], stories=[])
    out = run_script("validate-artifacts.py", "docs/epics", repo=tmp_path)
    assert out["artifacts_ok"] == "no"
    assert "no stories" in out["artifacts_errors"]


def test_missing_story_md_fails(tmp_path):
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}],
               stories=[{"slug": "s1", "covers": ["i1"], "write": False}])
    out = run_script("validate-artifacts.py", "docs/epics", repo=tmp_path)
    assert out["artifacts_ok"] == "no"
    assert "story.md missing" in out["artifacts_errors"]


def test_all_qa_passed_has_no_selectable_story(tmp_path):
    body = (
        "---\ntype: story\nslug: s1\nstatus: qa passed\n---\n# Story s1\n\n"
        "## Context\n\nx\n\n## Acceptance Criteria\n\n- y\n\n"
        "## Implementation Status\n\n- **Status**: QA passed\n"
    )
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}],
               stories=[{"slug": "s1", "covers": ["i1"], "body": body}])
    out = run_script("validate-artifacts.py", "docs/epics", repo=tmp_path)
    assert out["artifacts_ok"] == "no"
    assert "selectable" in out["artifacts_errors"]
