from __future__ import annotations

import json
from pathlib import Path

from ostler import crud, doctor, select
from ostler.model import load

from conftest import present


def test_create_epic_allocates_id_and_parses(tmp_path: Path):
    g = load(tmp_path)
    res = crud.create_epic(g, "billing", "Billing at parity", prefix="acme")
    assert res.ok
    # The directory carries the creation order; the slug still names the epic everywhere.
    assert res.entity_name == "0001-billing"
    g2 = load(tmp_path)
    assert g2.profile == "full"
    epic = select.epic_by_name(g2, "billing")
    assert epic is not None
    assert epic.eid.startswith("acme-") and epic.title == "Billing at parity"
    assert len(epic.eid.split("-", 1)[1]) == 26   # a ULID body, not a counter
    # registry pins the prefix (no counter — ULIDs need no persisted sequence)
    ids = json.loads((tmp_path / ".agents/ids.json").read_text())
    assert ids["prefix"] == "acme" and "counter" not in ids


def test_create_story_adds_block_and_scaffold(tmp_path: Path):
    g = load(tmp_path)
    crud.create_epic(g, "billing", "Billing", prefix="acme")
    crud.add_seed(load(tmp_path), "billing", "apercu-body", status="researched", summary="the body")
    res = crud.create_story(load(tmp_path), "billing", "01-apercu", "Aperçu body",
                            covers=["apercu-body"], depends=[])
    assert res.ok
    g2 = load(tmp_path)
    epic = select.epic_by_name(g2, "billing")
    assert epic is not None
    story = epic.stories[0]
    assert story.slug == "01-apercu"
    assert story.seed_items == ["apercu-body"]
    assert story.story_md and story.story_md.exists()
    assert {s.id for s in epic.seeds} == {"apercu-body"}

    # A scaffold is not an authored story. This is the whole incident in one assertion: an
    # author run created 44 of these, every checker read the scaffolded headings as evidence of
    # writing, and the run reported success. `create_story` succeeds; the story is unwritten
    # until somebody writes it, and `doctor` says so by name.
    assert story.unwritten_sections == ["Context", "Acceptance Criteria"]
    assert story.authored is False
    unwritten = [f for f in doctor.run(g2).findings if f.code == "unwritten-story"]
    assert [f.ref for f in unwritten] == ["01-apercu"]
    assert "Context, Acceptance Criteria are empty" in unwritten[0].message


def test_set_status_updates_frontmatter_and_line(repo: Path):
    res = crud.set_status(load(repo), "01-foo", "QA passed")
    assert res.ok
    g = load(repo)
    _, story = present(g.find_story("01-foo"))
    assert story.status == "QA passed"


def test_set_status_rewrites_only_the_field_not_the_prose(tmp_path: Path):
    """A story may legitimately write about status and about QA passing. Neither is the field.

    Both halves used to be text operations — a ``re.sub`` to write, a substring scan to read —
    so a Context paragraph containing "QA passed" or a criterion headed "Status" was
    indistinguishable from the ``- **Status**:`` bullet. Writing could hit the wrong line and
    reading could return the wrong value; a story could report itself done on the strength of
    its own prose. Both are now the parsed bullet, so the round-trip is exact and the
    surrounding text comes back byte-identical.
    """
    g = load(tmp_path)
    epic_dir = crud.create_epic(g, "billing", "Billing", prefix="acme").entity_name
    crud.create_story(load(tmp_path), "billing", "01-apercu", "Aperçu")
    story_md = tmp_path / f"docs/epics/{epic_dir}/stories/01-apercu/story.md"
    prose = (
        "- The legacy screen's QA passed in 4.2; hold that behaviour.\n"
        "- Status is shown in the header — do not move it.\n"
    )
    story_md.write_text(
        story_md.read_text(encoding="utf-8").replace("## Context\n", f"## Context\n\n{prose}"),
        encoding="utf-8",
    )
    before = story_md.read_text(encoding="utf-8")

    assert crud.set_status(load(tmp_path), "01-apercu", "In progress").ok
    after = story_md.read_text(encoding="utf-8")

    assert prose in after, "the prose lines must survive the status write untouched"
    assert after.count("Status") == before.count("Status"), "no line gained or lost the word"
    assert "- **Status**: In progress" in after
    # And the value reads back as the field — not as whatever the prose happens to say.
    assert present(load(tmp_path).find_story("01-apercu"))[1].status == "In progress"


def test_status_is_read_as_the_field_even_when_the_prose_says_qa_passed(tmp_path: Path):
    """The read half on its own: prose mentioning "QA passed" must not make a story done."""
    g = load(tmp_path)
    epic_dir = crud.create_epic(g, "billing", "Billing", prefix="acme").entity_name
    crud.create_story(load(tmp_path), "billing", "01-apercu", "Aperçu")
    story_md = tmp_path / f"docs/epics/{epic_dir}/stories/01-apercu/story.md"
    story_md.write_text(
        story_md.read_text(encoding="utf-8").replace(
            "## Context\n", "## Context\n\nThe old report QA passed before the rewrite.\n"),
        encoding="utf-8",
    )
    _, story = present(load(tmp_path).find_story("01-apercu"))
    assert story.status == "Not started"
    assert not select.is_done(story.status)


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


def test_story_frontmatter_carries_the_allocated_id(repo: Path):
    """A story.md is read on its own constantly — by the coder workflow picking up work, by
    `ostler trace`, by a human opening the file. Without the id in its own frontmatter the
    story cannot be named from the file itself; you have to go back to the parent epic and
    match on slug. Ids are ostler-minted and repo-prefixed."""
    crud.add_seed(load(repo), "epic-a", "s1", status="researched")
    res = crud.create_story(load(repo), "epic-a", "01-ided", "Has an id", covers=["s1"])
    assert res.ok and res.entity_id

    import yaml as _yaml
    text = (repo / "docs/epics/epic-a/stories/01-ided/story.md").read_text(encoding="utf-8")
    fm = _yaml.safe_load(text.split("---")[1])
    assert fm["id"] == res.entity_id, "the allocated id must be in the story's own frontmatter"
    # And the graph exposes it as a first-class field, mirroring Epic.eid.
    found = load(repo).find_story("01-ided")
    assert found is not None and found[1].eid == res.entity_id


def test_story_id_uses_the_repo_prefix(tmp_path: Path):
    """Prefix is the first four letters of the repo name, uppercased — so `todo-app` mints
    TODO-n. Ostler alone mints ids."""
    root = tmp_path / "todo-app"
    (root / "docs").mkdir(parents=True)
    crud.create_epic(load(root), "e1", "E1")
    crud.add_seed(load(root), "e1", "s1", status="researched")
    res = crud.create_story(load(root), "e1", "01-x", "X", covers=["s1"])
    assert res.entity_id.startswith("TODO-"), res.entity_id
