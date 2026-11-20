"""A story reads and writes only the Python book, and no markdown book page."""
from __future__ import annotations

from pathlib import Path

import pytest
from workhorse.templates import render

from workhorse_workflows.coder.shared import roles

CODER = Path(roles.__file__).resolve().parent.parent
PROMPTS = (
    "docs/prompts/specify-story.md",
    "book_qa/prompts/qa-book.md",
    "dev/prompts/_dev-inputs.md",
    "dev/prompts/_dev-scope.md",
)
BOOK_PATHS = ["services/api/journeys/publish.py"]


def _rendered(prompt: str, tmp_path: Path, with_skill: bool, **args: object) -> str:
    repo = tmp_path / "repo"
    if with_skill:
        skill = repo / ".claude/skills/ostler-book/SKILL.md"
        skill.parent.mkdir(parents=True)
        _ = skill.write_text("---\nname: ostler-book\n---\n", encoding="utf-8")
    (repo / ".git").mkdir(parents=True, exist_ok=True)
    base = {
        "_node_cwd": str(repo),
        "spec_dir": "specs/STORY-1",
        "services": ["api"],
        "story_services": ["api"],
        "book_services": ["api"],
        "spec_book_paths": BOOK_PATHS,
        "opening_brief": "",
        "follow_up_title": "",
        "report": "",
        "operator_context": "",
    }
    return render(prompt, base | args, CODER)


@pytest.mark.parametrize("with_skill", [True, False])
@pytest.mark.parametrize("prompt", PROMPTS)
def test_no_prompt_of_the_book_only_path_names_the_markdown_book(
    prompt: str, with_skill: bool, tmp_path: Path
) -> None:
    text = _rendered(prompt, tmp_path, with_skill)

    assert "docs/services" not in text
    assert "ostler doctor" not in text
    assert "ostler-okf" not in text


def test_the_spec_prompt_ends_on_the_book_check_and_says_the_claims_are_red_until_the_build(
    tmp_path: Path,
) -> None:
    text = _rendered("docs/prompts/specify-story.md", tmp_path, True)

    assert "ostler book check services.<name>" in text
    assert "expected to fail against\nthe current app until the build" in text
    assert "Write no markdown page" not in text


def test_the_dev_scope_names_the_book_only_when_a_service_has_one(tmp_path: Path) -> None:
    booked = _rendered("dev/prompts/_dev-scope.md", tmp_path / "booked", True)
    unbooked = _rendered("dev/prompts/_dev-scope.md", tmp_path / "unbooked", False, book_services=[])

    assert "## The book" in booked
    assert "## The book" not in unbooked


def test_the_dev_prompt_lists_the_book_paths_as_the_spec(tmp_path: Path) -> None:
    text = _rendered("dev/prompts/_dev-inputs.md", tmp_path, True)

    assert "## The book is this story's spec (executable books)" in text
    assert "`services/api/journeys/publish.py`" in text


def test_the_book_seat_keeps_source_pointers_and_the_index_current(tmp_path: Path) -> None:
    text = _rendered("book_qa/prompts/qa-book.md", tmp_path, True)

    assert "`source=` pointers and\n   `index.tsv` current" in text


QA_PROMPTS = ("qa/prompts/qa-story.md",)
UNREACHED = ["the export lands in the mailbox", "the audit line names the actor"]
QA_ARGS = {
    "story_path": "stories/STORY-1.md",
    "story_slug": "story-1",
    "story_id": "STORY-1",
    "epic": "E-1",
    "qa_dir": "qa",
    "qa_scratch_dir": "qa",
    "docs_root": "/work/acme",
    "target_env": "local",
    "runtime_python": "python",
    "verification_setup": None,
    "fixtures": [],
    "shared_packages": [],
    "qa_run_plan": [],
    "plan_services": "",
    "qa_only_scenarios": [],
    "standing_plan": False,
    "book_services": ["api"],
    "book_unreached": UNREACHED,
    "lease": "story-1-run",
    "result_schema": "{}",
    "failed_scenarios": [],
}


def _qa_rendered(tmp_path: Path, with_skill: bool, **args: object) -> str:
    return _rendered("qa/prompts/qa-story.md", tmp_path, with_skill, **(QA_ARGS | args))


@pytest.mark.parametrize("with_skill", [True, False])
@pytest.mark.parametrize("standing", [True, False])
def test_the_scenario_prompt_of_an_all_covered_story_names_no_markdown_page(
    standing: bool, with_skill: bool, tmp_path: Path
) -> None:
    text = _qa_rendered(tmp_path, with_skill, standing_plan=standing)

    for needle in ("docs/services", "okf:", "ostler-okf", "qa-stack.md", "ostler doctor", "ostler qa compile-plan"):
        assert needle not in text, needle


def test_the_scenario_prompt_of_an_all_covered_story_states_its_scope_as_numbered_claims(
    tmp_path: Path,
) -> None:
    text = _qa_rendered(tmp_path, True)

    assert "`claim:1`: the export lands in the mailbox" in text
    assert "`claim:2`: the audit line names the actor" in text
    assert 'covers=["claim:<n>"]' in text
    assert "are your whole\n   scope" in text


def test_the_scenario_prompt_of_an_all_covered_story_brings_the_stack_up_from_the_environment(
    tmp_path: Path,
) -> None:
    text = _qa_rendered(tmp_path, True)

    assert "ostler env up --copy story-1-run" in text
    assert "ostler env address <service> --copy story-1-run" in text


def test_the_scenario_prompt_of_a_story_with_no_service_book_covers_every_acceptance_criterion(
    tmp_path: Path,
) -> None:
    text = _qa_rendered(tmp_path, True, book_services=[], book_unreached=[])

    assert "No service book judged this story. The plan covers every Acceptance Criterion." in text
    assert 'covers=["ac:<n>"]' in text
    assert "criterion named `ac:<n>`" in text
    assert "`claim:1`" not in text
