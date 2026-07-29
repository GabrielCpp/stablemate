"""Tests for select-epic.py — the per-epic loop driver (OKF / ostler model)."""
from __future__ import annotations

from conftest import (
    init_repo,
    run_script,
    scaffold_story_body,
    write_epic,
    write_story,
)


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


def test_epic_of_bare_scaffolds_is_pending(tmp_path):
    """A rerun must resume an epic whose stories are all `ostler create story` scaffolds.

    This is what made the failed run unrecoverable: every story.md existed, so the epic read as
    complete and a rerun ended immediately with `has_epic == "no"` — there was no way to make
    the workflow finish its own work short of deleting the stubs by hand.
    """
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}, {"id": "i2"}],
               stories=[{"slug": "s1", "covers": ["i1"]}, {"slug": "s2", "covers": ["i2"]}])
    write_story(tmp_path, "e1", "s1", body=scaffold_story_body("s1"))
    write_story(tmp_path, "e1", "s2", body=scaffold_story_body("s2"))

    out = run_script("select-epic.py", "docs/epics", repo=tmp_path)
    assert out["has_epic"] == "yes"
    assert out["epic"] == "e1"


def test_epic_with_no_stories_is_incomplete(tmp_path):
    # epic.md exists and is queued but lists no stories → not complete, so it is selected.
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}], stories=[])

    out = run_script("select-epic.py", "docs/epics", repo=tmp_path)
    assert out["has_epic"] == "yes"
    assert out["epic"] == "e1"
