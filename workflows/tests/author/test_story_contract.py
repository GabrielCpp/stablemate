from __future__ import annotations

import logging
from pathlib import Path

from ostler import Ostler

from workhorse_workflows.author.main.nodes.stories import validate_story


def _authored_story(repo: Path, technical_notes: str) -> str:
    okf = Ostler(repo)
    okf.create_epic("parser", "Parser", prefix="acme")
    assert okf.create_story("parser", "safe-ast", "Safe AST").ok
    story_dir = "docs/epics/0001-parser/stories/safe-ast"
    path = repo / story_dir / "story.md"
    text = path.read_text(encoding="utf-8")
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
