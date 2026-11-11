"""A story whose services all have an executable book reads and writes no markdown book page."""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import pytest
from workhorse.templates import render

from workhorse_workflows.coder.shared import roles
from workhorse_workflows.coder.shared.okf import build_okf_context

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
        "markdown_services": [],
        "spec_nodes": [],
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


def test_the_dev_prompt_lists_the_book_paths_as_the_spec(tmp_path: Path) -> None:
    text = _rendered("dev/prompts/_dev-inputs.md", tmp_path, True)

    assert "## The book is this story's spec (executable books)" in text
    assert "`services/api/journeys/publish.py`" in text


def test_the_book_seat_keeps_source_pointers_and_the_index_current(tmp_path: Path) -> None:
    text = _rendered("book_qa/prompts/qa-book.md", tmp_path, True)

    assert "`source=` pointers and\n   `index.tsv` current" in text


def test_a_mixed_story_keeps_the_markdown_instructions_for_the_uncovered_service(
    tmp_path: Path,
) -> None:
    text = _rendered(
        "dev/prompts/_dev-scope.md", tmp_path, True, story_services=["api", "web"], markdown_services=["web"]
    )

    assert "executable book under `services/<name>/`" in text
    assert "under `docs/services/`" in text


def test_a_story_with_no_covered_service_keeps_the_markdown_instructions(tmp_path: Path) -> None:
    text = _rendered(
        "dev/prompts/_dev-scope.md", tmp_path, True, book_services=[], markdown_services=["web"], spec_book_paths=[]
    )

    assert "under `docs/services/`" in text
    assert "executable book under" not in text


def test_the_scenario_packet_of_an_all_covered_story_passes_with_no_obligation(
    repo: Path,
    write: Callable[[Path, str], Path],
    git: Callable[..., object],
) -> None:
    logger = logging.getLogger("test")
    write(repo / "services" / "api" / "service.py", "SERVICE = 1\n")
    write(repo / "app" / "a.py", "x = 1\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "the app")
    write(repo / "app" / "a.py", "x = 2\n")

    def packet(book_only: bool):
        return build_okf_context(
            logger,
            str(repo / "specs" / "S1"),
            "",
            str(repo / "docs" / "services"),
            ("api=app",),
            "HEAD",
            "WORKTREE",
            repo_dir=str(repo),
            book_only=book_only,
        )

    assert packet(False).status == "invalid"
    covered = packet(True)
    assert covered.status == "passed", covered
    assert "executable book" in covered.notes
