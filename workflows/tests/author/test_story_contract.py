from __future__ import annotations

import logging
from pathlib import Path

import pytest
from _books import write_book
from _workspace import lay_out, name_members, run_git
from _epics import epics_root
from ostler import Ostler

from workhorse_workflows.author.shared.nodes.services import service_errors
from workhorse_workflows.author.shared.nodes.stories import validate_story
from workhorse_workflows.author.shared.paths import survey_repo_root


def _authored_story(
    repo: Path, technical_notes: str, services: tuple[str, ...] = ("api-service",)
) -> str:
    write_book(repo, "api-service")
    okf = Ostler(repo)
    okf.create_epic("parser", "Parser")
    assert okf.create_story("parser", "safe-ast", "Safe AST").ok
    story_dir = str(epics_root() / "0001-parser/stories/safe-ast")
    path = repo / story_dir / "story.md"
    text = path.read_text(encoding="utf-8")
    if services:
        text = text.replace("\n---\n", f"\nservices: [{', '.join(services)}]\n---\n", 1)
    text = text.replace("## Context\n", "## Context\n\nCompile formulas safely.\n")
    text = text.replace(
        "## Acceptance Criteria\n",
        "## Acceptance Criteria\n\n- The compiler emits a safe AST.\n",
    )
    text = text.replace(
        "## Non-Functional Acceptance Criteria\n",
        "## Non-Functional Acceptance Criteria\n\n- Existing formula results remain unchanged.\n",
    )
    text = text.replace("## Technical Notes\n", f"## Technical Notes\n\n{technical_notes}\n")
    path.write_text(text, encoding="utf-8")
    return story_dir


def test_technical_notes_require_a_grounded_code_pointer(
    logger: logging.Logger, repo: Path
) -> None:
    """This fails when prose-only mechanics can masquerade as implementation evidence."""
    story_dir = _authored_story(repo, "The old parser traverses expressions recursively.")

    result = validate_story(logger, story_dir=story_dir, repo_dir=str(repo))

    assert result.ok is False
    assert "path::symbol" in result.errors


def test_technical_notes_accept_an_existing_code_pointer(
    logger: logging.Logger, repo: Path
) -> None:
    """This fails when an exact prior implementation pointer cannot satisfy the contract."""
    source = repo / "legacy" / "parser.py"
    source.parent.mkdir(parents=True)
    source.write_text("def parse_ast():\n    pass\n", encoding="utf-8")
    story_dir = _authored_story(
        repo,
        "- `legacy/parser.py::parse_ast` recursively maps the supported expression nodes.",
    )

    result = validate_story(logger, story_dir=story_dir, repo_dir=str(repo))

    assert result.ok is True, result.errors


def test_technical_notes_reject_a_pointer_outside_the_repository(
    logger: logging.Logger, repo: Path
) -> None:
    """This fails when traversal can masquerade as repository-grounded evidence."""
    outside = repo.parent / "outside.py"
    outside.write_text("def parse_ast():\n    pass\n", encoding="utf-8")
    story_dir = _authored_story(
        repo,
        f"- `../{outside.name}::parse_ast` maps the supported expression nodes.",
    )

    result = validate_story(logger, story_dir=story_dir, repo_dir=str(repo))

    assert result.ok is False
    assert "names no file under the repository" in result.errors


def test_technical_notes_allow_an_explicit_absence_of_prior_implementation(
    logger: logging.Logger, repo: Path
) -> None:
    """This fails when genuinely greenfield work is forced to invent a code pointer."""
    story_dir = _authored_story(repo, "No prior implementation reference exists.")

    result = validate_story(logger, story_dir=story_dir, repo_dir=str(repo))

    assert result.ok is True, result.errors


def test_technical_notes_require_the_exact_greenfield_statement(
    logger: logging.Logger, repo: Path
) -> None:
    """This fails when the exception can be buried in contradictory prose."""
    story_dir = _authored_story(
        repo,
        "No prior implementation reference exists. Maybe there is one in another service.",
    )

    result = validate_story(logger, story_dir=story_dir, repo_dir=str(repo))

    assert result.ok is False
    assert "exact statement" in result.errors
    assert "alone as its whole body" in result.errors


_NOTES = "- `legacy/parser.py::parse_ast` recursively maps the supported expression nodes."


def _with_pointer(repo: Path) -> None:
    source = repo / "legacy" / "parser.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("def parse_ast():\n    pass\n", encoding="utf-8")


def test_a_story_that_lists_no_services_fails(logger: logging.Logger, repo: Path) -> None:
    _with_pointer(repo)
    story_dir = _authored_story(repo, _NOTES, services=())

    result = validate_story(logger, story_dir=story_dir, repo_dir=str(repo))

    assert result.ok is False
    assert "services" in result.errors


def test_a_story_that_names_an_unknown_book_fails(logger: logging.Logger, repo: Path) -> None:
    _with_pointer(repo)
    story_dir = _authored_story(repo, _NOTES, services=("ghost-service",))

    result = validate_story(logger, story_dir=story_dir, repo_dir=str(repo))

    assert result.ok is False
    assert "ghost-service" in result.errors


def _web_book(repo: Path) -> None:
    write_book(repo, "web-app", screens=True)


def test_a_story_with_a_ui_service_needs_a_mockup_beside_it(
    logger: logging.Logger, repo: Path
) -> None:
    _with_pointer(repo)
    _web_book(repo)
    story_dir = _authored_story(repo, _NOTES, services=("web-app",))

    missing = validate_story(logger, story_dir=story_dir, repo_dir=str(repo))
    (repo / story_dir / "mockup.html").write_text("<html></html>\n", encoding="utf-8")
    drawn = validate_story(logger, story_dir=story_dir, repo_dir=str(repo))

    assert missing.ok is False
    assert "mockup.html" in missing.errors
    assert drawn.ok is True, drawn.errors


def test_a_todo_written_as_the_products_noun_is_not_an_open_question(
    logger: logging.Logger, repo: Path
) -> None:
    """This fails when a todo app's stories trip the marker check on the word for what they build."""
    _with_pointer(repo)
    notes = f"{_NOTES}\n\nA person adds a Todo, the todo list shows it, and nothing is left to do."
    story_dir = _authored_story(repo, notes)

    result = validate_story(logger, story_dir=story_dir, repo_dir=str(repo))

    assert result.ok is True, result.errors


@pytest.mark.parametrize(
    "line",
    ["TODO pick the retry limit.", "todo: pick the retry limit.", "The retry limit is TBD."],
)
def test_a_marker_in_capitals_or_before_a_colon_is_an_open_question(
    logger: logging.Logger, repo: Path, line: str
) -> None:
    """This fails when narrowing the check to markers lets a real placeholder through."""
    _with_pointer(repo)
    story_dir = _authored_story(repo, f"{_NOTES}\n\n{line}")

    result = validate_story(logger, story_dir=story_dir, repo_dir=str(repo))

    assert result.ok is False
    assert "unresolved decision" in result.errors


def test_in_a_workspace_a_story_naming_an_artifacts_book_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    laid = lay_out(tmp_path, run_git)
    name_members(tmp_path, monkeypatch, laid)
    write_book(laid.artifacts, "api-service")

    errors = service_errors(Ostler(survey_repo_root(str(laid.api))), "the story", ["api-service"])

    assert errors == []


def test_in_a_workspace_a_book_only_in_a_member_repo_is_no_book(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    laid = lay_out(tmp_path, run_git)
    name_members(tmp_path, monkeypatch, laid)
    write_book(laid.api, "web-app")

    errors = service_errors(Ostler(survey_repo_root(str(laid.api))), "the story", ["web-app"])

    assert len(errors) == 1 and "web-app" in errors[0]
