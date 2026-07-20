from __future__ import annotations

import json
from pathlib import Path

from ostler import crud, doctor
from ostler.model import load


def test_create_epic_allocates_id_and_parses(tmp_path: Path):
    g = load(tmp_path)
    res = crud.create_epic(g, "billing", "Billing at parity", prefix="pred")
    assert res.ok
    g2 = load(tmp_path)
    assert g2.profile == "full"
    epic = next(e for e in g2.epics if e.name == "billing")
    assert epic.eid == "pred-1" and epic.title == "Billing at parity"
    # id registry advanced
    ids = json.loads((tmp_path / ".agents/ids.json").read_text())
    assert ids["prefix"] == "pred" and ids["counter"] == 2


def test_create_story_adds_block_and_scaffold(tmp_path: Path):
    g = load(tmp_path)
    crud.create_epic(g, "billing", "Billing", prefix="pred")
    crud.add_seed(load(tmp_path), "billing", "apercu-body", status="researched", summary="the body")
    res = crud.create_story(load(tmp_path), "billing", "01-apercu", "Aperçu body",
                            covers=["apercu-body"], depends=[])
    assert res.ok
    g2 = load(tmp_path)
    epic = next(e for e in g2.epics if e.name == "billing")
    story = epic.stories[0]
    assert story.slug == "01-apercu"
    assert story.seed_items == ["apercu-body"]
    assert story.story_md and story.story_md.exists()
    assert {s.id for s in epic.seeds} == {"apercu-body"}
    # clean graph (seed covered, story present)
    assert doctor.run(g2).errors == 0, [f.message for f in doctor.run(g2).findings if f.severity == "error"]


def test_set_status_updates_frontmatter_and_line(repo: Path):
    res = crud.set_status(load(repo), "01-foo", "QA passed")
    assert res.ok
    g = load(repo)
    story = g.find_story("01-foo")[1]
    assert story.status == "QA passed"


def test_delete_story_removes_block_and_dir(repo: Path):
    res = crud.delete_story(load(repo), "01-foo")
    assert res.ok
    assert not (repo / "docs/epics/epic-a/stories/01-foo").exists()
    g = load(repo)
    assert g.find_story("01-foo") is None


def test_seed_add_remove(repo: Path):
    assert crud.add_seed(load(repo), "epic-a", "new-seed", status="researched").ok
    assert any(s.id == "new-seed" for s in load(repo).epics[0].seeds)
    assert crud.remove_seed(load(repo), "epic-a", "new-seed").ok
    assert not any(s.id == "new-seed" for s in load(repo).epics[0].seeds)


def test_create_feature(tmp_path: Path):
    res = crud.create_feature(load(tmp_path), "signin", "Sign in", area="auth",
                              route="/signin", prefix="x")
    assert res.ok
    feats = load(tmp_path).features
    assert any(f.slug == "signin" and f.area == "auth" for f in feats)


# ── re-run idempotency ────────────────────────────────────────────────────────
# The author workflow's bounded rework loops re-run these stages, and two independent
# prompts document them as update-or-create: `write-epic.md` ("re-running `ostler seed add`
# updates it rather than duplicating") and `split-stories.md` ("`ostler create story` for an
# existing slug is a no-op"). Both used to return not-ok and exit 1, which turned every
# rework loop into a hard failure.

def test_add_seed_is_update_or_create(repo: Path):
    assert crud.add_seed(load(repo), "epic-a", "dup-seed", status="researched",
                         summary="first").ok
    res = crud.add_seed(load(repo), "epic-a", "dup-seed", status="covered",
                        summary="second")
    assert res.ok and "updated" in res.message
    seeds = [s for s in load(repo).epics[0].seeds if s.id == "dup-seed"]
    assert len(seeds) == 1, "re-running must update in place, never duplicate the block"
    assert seeds[0].status == "covered"


def test_create_story_existing_slug_is_a_noop(repo: Path):
    crud.add_seed(load(repo), "epic-a", "s1", status="researched")
    first = crud.create_story(load(repo), "epic-a", "01-dup", "Dup", covers=["s1"])
    assert first.ok
    story_md = repo / "docs/epics/epic-a/stories/01-dup/story.md"
    story_md.write_text(story_md.read_text(encoding="utf-8") + "\nhand-written body\n",
                        encoding="utf-8")

    second = crud.create_story(load(repo), "epic-a", "01-dup", "Dup", covers=["s1"])
    assert second.ok and "already exists" in second.message
    # The no-op must not re-allocate an id or clobber the body.
    assert "hand-written body" in story_md.read_text(encoding="utf-8")
    assert first.entity_id and second.entity_id in (None, "", first.entity_id)
