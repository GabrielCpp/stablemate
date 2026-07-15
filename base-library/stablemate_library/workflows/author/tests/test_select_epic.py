"""Tests for select-epic.py — the per-epic loop driver (OKF / ostler model)."""
from __future__ import annotations

from conftest import init_repo, requires_ostler, run_script, write_epic

pytestmark = requires_ostler


def test_empty_queue_returns_no(tmp_path):
    init_repo(tmp_path)  # root marker + docs/epics, but no epics queued
    out = run_script("select-epic.py", "docs/epics", repo=tmp_path)
    assert out["has_epic"] == "no"
    assert "queue is empty" in out["reason"]


def test_selects_first_incomplete_epic(tmp_path):
    # e1 fully authored; e2 lists a story whose story.md is missing → e2 selected.
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}], stories=[{"slug": "s1", "covers": ["i1"]}])
    write_epic(tmp_path, "e2", seeds=[{"id": "i2"}],
               stories=[{"slug": "s2", "covers": ["i2"], "write": False}])

    out = run_script("select-epic.py", "docs/epics", repo=tmp_path)
    assert out["has_epic"] == "yes"
    assert out["epic"] == "e2"
    assert out["epic_dir"] == "docs/epics/e2"


def test_all_authored_returns_no(tmp_path):
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}], stories=[{"slug": "s1", "covers": ["i1"]}])

    out = run_script("select-epic.py", "docs/epics", repo=tmp_path)
    assert out["has_epic"] == "no"


def test_epic_with_no_stories_is_incomplete(tmp_path):
    # epic.md exists and is queued but lists no stories → not complete, so it is selected.
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}], stories=[])

    out = run_script("select-epic.py", "docs/epics", repo=tmp_path)
    assert out["has_epic"] == "yes"
    assert out["epic"] == "e1"
