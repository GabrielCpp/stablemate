from __future__ import annotations

import json
from pathlib import Path

from ostler import doctor, edit, markdown
from ostler.model import load

from conftest import write


def _story_status(repo: Path, epic: str, slug: str) -> str:
    p = repo / f"docs/epics/{epic}/stories/{slug}/story.md"
    return (markdown.split(p.read_text()).frontmatter or {})["status"]


def _write_resolution(repo: Path, slug: str, verdict: dict) -> Path:
    p = repo / "docs/specs" / slug / edit.RESOLUTION_FILE
    write(p, json.dumps(verdict, indent=2))
    return p


def test_rename_cascades_and_stays_clean(repo: Path):
    graph = load(repo)
    plan = edit.rename(graph, "01-foo", "01-foofoo")
    assert plan.changes
    assert plan.moves
    plan.apply()

    assert (repo / "docs/epics/epic-a/stories/01-foofoo/story.md").exists()
    assert not (repo / "docs/epics/epic-a/stories/01-foo").exists()

    report = doctor.run(load(repo))
    assert report.errors == 0, [f.message for f in report.findings if f.severity == "error"]


def test_rename_does_not_touch_unrelated_substrings(repo: Path):
    story = repo / "docs/epics/epic-a/stories/01-foo/story.md"
    story.write_text(story.read_text() + "\nThe word foobar stays.\n", encoding="utf-8")
    plan = edit.rename(load(repo), "01-foo", "01-baz")
    plan.apply()
    moved = (repo / "docs/epics/epic-a/stories/01-baz/story.md").read_text()
    assert "foobar stays" in moved


def test_relink_replaces_path_everywhere(repo: Path):
    plan = edit.relink(load(repo), "../../../features/area/rec.md",
                       "../../../features/area/renamed.md")
    assert plan.changes
    plan.apply()
    story = (repo / "docs/epics/epic-a/stories/01-foo/story.md").read_text()
    assert "renamed.md" in story
    assert "rec.md" not in story


def test_edit_dry_run_writes_nothing(repo: Path):
    story = repo / "docs/epics/epic-a/stories/01-foo/story.md"
    before = story.read_text()
    plan = edit.relink(load(repo), "../../../features/area/rec.md", "../../../features/area/renamed.md")
    assert plan.changes
    assert story.read_text() == before


def test_relink_unknown_path_is_a_noop(repo: Path):
    plan = edit.relink(load(repo), "../../../features/area/nope.md", "../../../features/area/other.md")
    assert not plan.changes



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
    assert _story_status(repo, "epic-a", "01-foo") == "Not started"
    led = _ledger(repo, "01-foo")
    assert led["all_verified"] is False and led["any_blocked"] is False
    assert led["verified"] == ["Finding 1"]
    assert [o["id"] for o in led["open"]] == ["Finding 2"]
    assert "does not exist" in led["open"][0]["reason"]


def test_settle_review_unproven_artifact_leaves_open_not_applied(repo: Path):
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
    edit.settle_review(load(repo), "01-foo")
    assert _story_status(repo, "epic-a", "01-foo") == "Not started"
    assert not (spec / edit.SETTLEMENT_FILE).exists()


def test_settle_review_declined_with_reason_settles_and_applies(repo: Path):
    spec = repo / "docs/specs/01-foo"
    write(spec / "evidence/f1.png", "img")
    _write_resolution(repo, "01-foo", {
        "status": "applied",
        "findings": [
            {"id": "Finding 1", "disposition": "addressed", "artifacts": ["evidence/f1.png"]},
            {"id": "Finding 2", "disposition": "declined", "reason": "out of scope"},
        ],
    })
    plan = edit.settle_review(load(repo), "01-foo")
    assert not plan.error, plan.error
    plan.apply()
    assert _story_status(repo, "epic-a", "01-foo") == edit.STATUS_APPLIED
    led = _ledger(repo, "01-foo")
    assert led["declined"] == [{"id": "Finding 2", "reason": "out of scope"}]
    assert led["verified"] == ["Finding 1"]
    assert led["all_verified"] is False and led["all_settled"] is True


def test_settle_review_declined_without_reason_errors(repo: Path):
    _write_resolution(repo, "01-foo", {
        "findings": [{"id": "Finding 1", "disposition": "declined", "reason": "  "}],
    })
    plan = edit.settle_review(load(repo), "01-foo")
    assert plan.error and "Finding 1" in plan.error and "reason" in plan.error


def test_settle_review_ledger_only_leaves_story_status(repo: Path):
    spec = repo / "docs/specs/01-foo"
    write(spec / "evidence/f1.png", "img")
    _write_resolution(repo, "01-foo", {
        "findings": [{"id": "Finding 1", "disposition": "addressed",
                      "artifacts": ["evidence/f1.png"]}],
    })
    plan = edit.settle_review(load(repo), "01-foo", status_write=False)
    assert not plan.error, plan.error
    assert [c.path.name for c in plan.changes] == [edit.SETTLEMENT_FILE]
    plan.apply()
    assert _story_status(repo, "epic-a", "01-foo") == "Not started"
    assert _ledger(repo, "01-foo")["all_verified"] is True


def test_settle_review_ledger_only_skips_the_blocked_stamp(repo: Path):
    _write_resolution(repo, "01-foo", {
        "findings": [{"id": "Finding 1", "disposition": "blocked"}],
    })
    plan = edit.settle_review(load(repo), "01-foo", status_write=False)
    plan.apply()
    assert _story_status(repo, "epic-a", "01-foo") == "Not started"
    assert _ledger(repo, "01-foo")["any_blocked"] is True


def _write_answers(repo: Path, slug: str, text: str, filename: str = edit.ANSWERS_FILE) -> None:
    write(repo / "docs/specs" / slug / filename, text)


ANSWERS = (
    "# Answers\n\n"
    "## F-1: fixed\n\n- commit: abc1234\n- path: src/handler.py\n\n"
    "## F-2: declined\n\nReason: the api-service owns this.\n\n"
    "## F-9: fixed\n\n- test: test_nine\n\n"
    "## F-3: fixed\n\nNo evidence here.\n"
)


def test_settle_answers_sorts_filed_ids_by_answer(repo: Path):
    _write_answers(repo, "01-foo", ANSWERS)
    led = edit.settle_answers(load(repo), "01-foo", ["F-1", "F-2", "F-3", "F-4"])
    assert led["fixed"] == ["F-1"]
    assert led["declined"] == [{"id": "F-2", "reason": "the api-service owns this."}]
    assert led["open"] == ["F-3", "F-4"]
    assert led["unknown"] == ["F-9"]
    assert len(led["errors"]) == 1 and led["errors"][0].startswith("F-3:")
    assert sorted(led["answers"]) == ["F-1", "F-2"]
    assert led["answers"]["F-1"] == {"disposition": "fixed", "commits": ["abc1234"],
                                     "paths": ["src/handler.py"], "tests": [], "reason": ""}
    assert led["all_answered"] is False


def test_settle_answers_all_answered_when_nothing_open(repo: Path):
    _write_answers(repo, "01-foo", ANSWERS)
    led = edit.settle_answers(load(repo), "01-foo", ["F-1", "F-2", "F-1"])
    assert led["fixed"] == ["F-1"] and led["open"] == []
    assert led["all_answered"] is True


def test_settle_answers_missing_file_leaves_every_id_open(repo: Path):
    led = edit.settle_answers(load(repo), "01-foo", ["F-1", "F-2"])
    assert led["open"] == ["F-1", "F-2"] and led["errors"] == []
    assert led["fixed"] == [] and led["answers"] == {} and led["all_answered"] is False


def test_settle_answers_dry_run_writes_nothing(repo: Path):
    _write_answers(repo, "01-foo", ANSWERS)
    edit.settle_answers(load(repo), "01-foo", ["F-1"])
    assert not (repo / "docs/specs/01-foo" / edit.SETTLEMENT_FILE).exists()


def test_settle_answers_write_records_the_ledger_and_never_the_status(repo: Path):
    _write_answers(repo, "01-foo", ANSWERS)
    before = (repo / "docs/epics/epic-a/stories/01-foo/story.md").read_text()
    led = edit.settle_answers(load(repo), "01-foo", ["F-1", "F-2"], write=True)
    assert _ledger(repo, "01-foo") == led
    assert (repo / "docs/epics/epic-a/stories/01-foo/story.md").read_text() == before


def test_settle_answers_write_creates_a_missing_spec_dir(repo: Path):
    led = edit.settle_answers(load(repo), "01-foo", ["F-1"], write=True)
    assert _ledger(repo, "01-foo") == led and led["open"] == ["F-1"]


def test_settle_answers_reads_a_named_file(repo: Path):
    _write_answers(repo, "01-foo", "## F-1: fixed\n\n- commit: abc\n", filename="round-2.md")
    led = edit.settle_answers(load(repo), "01-foo", ["F-1"], filename="round-2.md")
    assert led["fixed"] == ["F-1"]
