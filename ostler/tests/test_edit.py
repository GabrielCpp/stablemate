from __future__ import annotations

import json
from pathlib import Path

from ostler import doctor, edit, markdown
from ostler.model import load

from conftest import knowledge_md, write


def _story_status(repo: Path, epic: str, slug: str) -> str:
    p = repo / f"docs/epics/{epic}/stories/{slug}/story.md"
    return (markdown.split(p.read_text()).frontmatter or {})["status"]


def _write_resolution(repo: Path, slug: str, verdict: dict) -> Path:
    p = repo / "docs/specs" / slug / edit.RESOLUTION_FILE
    write(p, json.dumps(verdict, indent=2))
    return p


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


# ── settle-review: per-finding, artifact-gated settlement (4.3) ──────────────────

def _ledger(repo: Path, slug: str) -> dict:
    p = repo / "docs/specs" / slug / edit.SETTLEMENT_FILE
    return json.loads(p.read_text())


def test_settle_review_applies_when_all_findings_verified(repo: Path):
    spec = repo / "docs/specs/01-foo"
    write(spec / "evidence/new-1280.png", "img")
    write(spec / "qa/observations.json", json.dumps({"form": {"headingLabel": "Foundation area"}}))
    _write_resolution(repo, "01-foo", {
        "status": "applied",
        "findings": [{
            "id": "Finding 1", "disposition": "addressed",
            "artifacts": ["evidence/new-1280.png"],
            "assertions": [{"file": "qa/observations.json",
                            "pointer": "form.headingLabel", "equals": "Foundation area"}],
        }],
    })
    plan = edit.settle_review(load(repo), "01-foo")
    assert not plan.error, plan.error
    plan.apply()
    assert _story_status(repo, "epic-a", "01-foo") == edit.STATUS_APPLIED
    led = _ledger(repo, "01-foo")
    assert led["all_verified"] is True and not led["any_blocked"]
    assert led["verified"] == ["Finding 1"] and led["open"] == []


def test_settle_review_partial_keeps_status_and_marks_open(repo: Path):
    # One finding proven, one whose screenshot was never captured: status must NOT flip
    # (still has an open finding), and the ledger names exactly which to re-apply.
    spec = repo / "docs/specs/01-foo"
    write(spec / "evidence/f1.png", "img")
    _write_resolution(repo, "01-foo", {
        "status": "applied",
        "findings": [
            {"id": "Finding 1", "disposition": "addressed", "artifacts": ["evidence/f1.png"]},
            {"id": "Finding 2", "disposition": "addressed", "artifacts": ["evidence/missing.png"]},
        ],
    })
    plan = edit.settle_review(load(repo), "01-foo")
    assert not plan.error, plan.error
    plan.apply()
    assert _story_status(repo, "epic-a", "01-foo") == "Not started"  # unchanged — still open
    led = _ledger(repo, "01-foo")
    assert led["all_verified"] is False and led["any_blocked"] is False
    assert led["verified"] == ["Finding 1"]
    assert [o["id"] for o in led["open"]] == ["Finding 2"]
    assert "does not exist" in led["open"][0]["reason"]


def test_settle_review_unproven_artifact_leaves_open_not_applied(repo: Path):
    # The finding claims a screenshot that was never captured → it stays OPEN (re-apply),
    # never silently flipping the story to applied. No hard error; the loop retries it.
    _write_resolution(repo, "01-foo", {
        "status": "applied",
        "findings": [{"id": "Finding 1", "disposition": "addressed",
                      "artifacts": ["evidence/new-1280.png"]}],
    })
    plan = edit.settle_review(load(repo), "01-foo")
    assert not plan.error
    plan.apply()
    assert _story_status(repo, "epic-a", "01-foo") == "Not started"
    led = _ledger(repo, "01-foo")
    assert led["all_verified"] is False
    assert [o["id"] for o in led["open"]] == ["Finding 1"]


def test_settle_review_broadened_assertion_leaves_open_not_applied(repo: Path):
    # The oracle was weakened to the WRONG value (the gaming move) — exact-match keeps the
    # finding OPEN, so the story is never flipped to applied on a fabricated resolution.
    spec = repo / "docs/specs/01-foo"
    write(spec / "qa/observations.json", json.dumps({"form": {"headingLabel": "Surface"}}))
    _write_resolution(repo, "01-foo", {
        "status": "applied",
        "findings": [{"id": "Finding 1", "disposition": "addressed",
                      "assertions": [{"file": "qa/observations.json",
                                      "pointer": "form.headingLabel", "equals": "Foundation area"}]}],
    })
    plan = edit.settle_review(load(repo), "01-foo")
    assert not plan.error
    plan.apply()
    assert _story_status(repo, "epic-a", "01-foo") == "Not started"
    led = _ledger(repo, "01-foo")
    assert led["all_verified"] is False
    assert "expected exactly" in led["open"][0]["reason"]


def test_settle_review_blocked_finding_stamps_blocked_and_escalates(repo: Path):
    # A blocked finding escalates individually even alongside a verified one: status →
    # Blocked, ledger reports any_blocked while still recording the verified finding.
    spec = repo / "docs/specs/01-foo"
    write(spec / "evidence/f1.png", "img")
    _write_resolution(repo, "01-foo", {
        "status": "applied",
        "findings": [
            {"id": "Finding 1", "disposition": "addressed", "artifacts": ["evidence/f1.png"]},
            {"id": "Finding 2", "disposition": "blocked"},
        ],
    })
    plan = edit.settle_review(load(repo), "01-foo")
    assert not plan.error, plan.error
    plan.apply()
    assert _story_status(repo, "epic-a", "01-foo") == edit.STATUS_BLOCKED
    led = _ledger(repo, "01-foo")
    assert led["any_blocked"] is True and led["blocked"] == ["Finding 2"]
    assert led["verified"] == ["Finding 1"]


def test_settle_review_unknown_disposition_errors(repo: Path):
    _write_resolution(repo, "01-foo", {
        "findings": [{"id": "Finding 1", "disposition": "maybe"}],
    })
    plan = edit.settle_review(load(repo), "01-foo")
    assert plan.error and "unknown disposition" in plan.error


def test_settle_review_missing_resolution_errors(repo: Path):
    plan = edit.settle_review(load(repo), "01-foo")
    assert plan.error and edit.RESOLUTION_FILE in plan.error


def test_settle_review_dry_run_writes_nothing(repo: Path):
    spec = repo / "docs/specs/01-foo"
    write(spec / "evidence/new-1280.png", "img")
    _write_resolution(repo, "01-foo", {
        "status": "applied",
        "findings": [{"id": "Finding 1", "disposition": "addressed",
                      "artifacts": ["evidence/new-1280.png"]}],
    })
    edit.settle_review(load(repo), "01-foo")  # build plan, do not apply
    assert _story_status(repo, "epic-a", "01-foo") == "Not started"
    assert not (spec / edit.SETTLEMENT_FILE).exists()  # ledger only written on apply
