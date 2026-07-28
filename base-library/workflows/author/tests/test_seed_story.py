"""Tests for seed-story.py — story-mode registration of one bullet into an existing epic.

Under the OKF model the script adds one seed to the epic's ``epic.md`` (``ostler seed add``) and
creates one story (``ostler create story``, which scaffolds ``story.md`` and allocates the id).
Seeds/stories are read back via ostler. A test asserts the emitted JSON plus the resulting graph
(the seed and story ostler now sees).
"""
from __future__ import annotations

import json
import subprocess

from conftest import (
    init_repo, requires_ostler, run_script, run_script_raw, write_backlog, write_epic,
)

pytestmark = requires_ostler


def _seeds(repo, epic):
    p = subprocess.run(["ostler", "list", "--type", "seed", "--epic", epic, "--json"],
                       cwd=str(repo), capture_output=True, text=True)
    return json.loads(p.stdout[p.stdout.find("["):])


def _seed_ids(repo, epic):
    return [s["id"] for s in _seeds(repo, epic)]


def _stories(repo, epic):
    p = subprocess.run(["ostler", "list", "--type", "story", "--epic", epic, "--json"],
                       cwd=str(repo), capture_output=True, text=True)
    return json.loads(p.stdout[p.stdout.find("["):])


def test_missing_epic_fails(tmp_path):
    init_repo(tmp_path)
    proc = run_script_raw("seed-story.py", "ghost", "docs/epics", "feat-x", repo=tmp_path)
    assert proc.returncode != 0
    assert "does not exist" in proc.stderr


def test_missing_epic_arg_fails(tmp_path):
    init_repo(tmp_path)
    proc = run_script_raw("seed-story.py", "", "docs/epics", "feat-x", repo=tmp_path)
    assert proc.returncode != 0
    assert "no epic" in proc.stderr


def test_missing_bullet_arg_fails(tmp_path):
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}], stories=[{"slug": "s1", "covers": ["i1"]}])
    proc = run_script_raw("seed-story.py", "e1", "docs/epics", "", repo=tmp_path)
    assert proc.returncode != 0
    assert "no bullet" in proc.stderr


def test_backlog_id_bullet_resolves_and_marks_from_backlog(tmp_path):
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}],
               stories=[{"slug": "existing-s1", "covers": ["i1"]}])
    write_backlog(tmp_path, ["the-new-thing"])
    out = run_script("seed-story.py", "e1", "docs/epics", "the-new-thing", repo=tmp_path)

    slug = out["story_slug"]
    assert out["bullet_id"] == "the-new-thing"
    assert out["from_backlog"] == "yes"
    assert out["epic_dir"] == "docs/epics/e1"
    assert out["story_dir"] == f"docs/epics/e1/stories/{slug}"
    assert out["story_path"] == f"docs/epics/e1/stories/{slug}/story.md"
    # one seed item appended for the resolved id
    assert _seed_ids(tmp_path, "e1").count("the-new-thing") == 1
    # one story appended covering that seed id, with its story.md scaffolded on disk
    story = next(s for s in _stories(tmp_path, "e1") if s["slug"] == slug)
    assert story["covers"] == ["the-new-thing"]
    assert (tmp_path / out["story_path"]).is_file()


def test_bracketed_id_form_accepted(tmp_path):
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}], stories=[{"slug": "01-s1", "covers": ["i1"]}])
    write_backlog(tmp_path, ["bracket-thing"])
    out = run_script("seed-story.py", "e1", "docs/epics", "[bracket-thing]", repo=tmp_path)
    assert out["bullet_id"] == "bracket-thing"
    assert out["from_backlog"] == "yes"


def test_literal_bullet_derives_kebab_id(tmp_path):
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}], stories=[{"slug": "item-1", "covers": ["i1"]}])
    out = run_script("seed-story.py", "e1", "docs/epics", "Add a Shiny New Thing!", repo=tmp_path)
    assert out["bullet_id"] == "add-a-shiny-new-thing"
    assert out["from_backlog"] == "no"
    # the verbatim bullet text becomes the seed's sourceBullet
    seeds = subprocess.run(["ostler", "list", "--type", "seed", "--epic", "e1", "--json"],
                           cwd=str(tmp_path), capture_output=True, text=True).stdout
    rows = json.loads(seeds[seeds.find("["):])
    item = next(s for s in rows if s["id"] == "add-a-shiny-new-thing")
    assert item["sourceBullet"] == "Add a Shiny New Thing!"


def test_sequential_stories_get_distinct_slugs(tmp_path):
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}], stories=[{"slug": "item-1", "covers": ["i1"]}])
    first = run_script("seed-story.py", "e1", "docs/epics", "second-thing", repo=tmp_path)
    second = run_script("seed-story.py", "e1", "docs/epics", "third-thing", repo=tmp_path)
    assert first["story_slug"] != second["story_slug"]


def test_idempotent_rerun_reuses_story(tmp_path):
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}], stories=[{"slug": "01-s1", "covers": ["i1"]}])
    write_backlog(tmp_path, ["dup-thing"])
    first = run_script("seed-story.py", "e1", "docs/epics", "dup-thing", repo=tmp_path)
    second = run_script("seed-story.py", "e1", "docs/epics", "dup-thing", repo=tmp_path)

    assert first["story_slug"] == second["story_slug"]
    assert "idempotent" in second["reason"] or "reusing" in second["reason"]
    # no duplicate seed item or story for the resolved id
    assert _seed_ids(tmp_path, "e1").count("dup-thing") == 1
    assert [s["slug"] for s in _stories(tmp_path, "e1")].count(first["story_slug"]) == 1


def test_literal_bullet_not_in_backlog_is_not_from_backlog(tmp_path):
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}], stories=[{"slug": "01-s1", "covers": ["i1"]}])
    write_backlog(tmp_path, ["something-else"])
    out = run_script("seed-story.py", "e1", "docs/epics", "Totally unrelated work", repo=tmp_path)
    assert out["from_backlog"] == "no"


def test_scoped_backlog_resolves_bullet_verbatim(tmp_path):
    """A run scoped to a non-default backlog resolves against THAT file, so the tail prunes it."""
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}], stories=[{"slug": "01-s1", "covers": ["i1"]}])
    write_backlog(tmp_path, ["rewrite-thing"])
    write_backlog(tmp_path, ["scoped-thing"], texts={"scoped-thing": "build the scoped thing"},
                  path="docs/backlog-scoped.md")
    out = run_script("seed-story.py", "e1", "docs/epics", "scoped-thing", "docs/knowledge",
                     "docs/backlog-scoped.md", repo=tmp_path)
    assert out["bullet_id"] == "scoped-thing"
    # from_backlog gates story_prune; "no" here would leave the bullet in the scoped backlog forever
    assert out["from_backlog"] == "yes"
    seed = next(s for s in _seeds(tmp_path, "e1") if s["id"] == "scoped-thing")
    assert seed.get("sourceBullet") == "[scoped-thing] build the scoped thing"


def test_default_backlog_still_used_when_arg_omitted(tmp_path):
    """Callers that pass no backlog arg keep resolving against docs/backlog.md."""
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}], stories=[{"slug": "01-s1", "covers": ["i1"]}])
    write_backlog(tmp_path, ["default-thing"])
    out = run_script("seed-story.py", "e1", "docs/epics", "default-thing", repo=tmp_path)
    assert out["from_backlog"] == "yes"


def test_bullet_from_the_other_backlog_is_not_from_backlog(tmp_path):
    """Scoping is real: a bullet living only in the unscoped backlog is not consumed by this run."""
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}], stories=[{"slug": "01-s1", "covers": ["i1"]}])
    write_backlog(tmp_path, ["rewrite-thing"])
    write_backlog(tmp_path, ["scoped-thing"], path="docs/backlog-scoped.md")
    out = run_script("seed-story.py", "e1", "docs/epics", "rewrite-thing", "docs/knowledge",
                     "docs/backlog-scoped.md", repo=tmp_path)
    assert out["from_backlog"] == "no"
