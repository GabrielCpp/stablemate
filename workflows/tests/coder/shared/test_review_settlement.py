"""A "not a defect" decline settles only behind a test that exists, and no other decline needs one."""
from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from ostler import Ostler
from workhorse_workflows.coder.shared.review import ANSWERS_FILE, coincidence_gap, settle_findings

FINDING = "acme-story/review-1.4"


@pytest.fixture
def code_repo(
    tmp_path: Path,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
) -> Path:
    root = tmp_path / "api-service"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    write(root / "tests" / "test_redirect.py", "def test_keeps_trailing_slash_on_redirect():\n    pass\n")
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "Initial commit")
    return root


def _settle(
    repo: Path,
    code_repo: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    answer: str,
    reuse: list[str] | None = None,
):
    okf = Ostler(repo)
    assert okf.create_epic("acme-epic", "Acme epic", prefix="acme").ok
    created = okf.create_story("acme-epic", "acme-story", "Acme story")
    assert created.ok
    write(Path(okf.spec_path(created.entity_id)) / ANSWERS_FILE, answer)
    return settle_findings(
        logger,
        story_slug="acme-story",
        story_id=created.entity_id,
        filed=[FINDING],
        repos=[str(code_repo)],
        repo_dir=str(repo),
        reuse=reuse,
    )


def test_a_not_a_defect_decline_with_no_test_comes_back_open(
    repo: Path, code_repo: Path, logger: logging.Logger, write: Callable[[Path, str], Path]
) -> None:
    settlement = _settle(
        repo, code_repo, logger, write,
        f"## {FINDING}: declined\nReason: not a defect. The redirect already keeps the slash.\n",
    )

    assert settlement.declined == []
    assert settlement.open == [FINDING]
    assert "cites no test" in settlement.rejected[FINDING]


def test_a_not_a_defect_decline_citing_a_tracked_test_settles_as_declined(
    repo: Path, code_repo: Path, logger: logging.Logger, write: Callable[[Path, str], Path]
) -> None:
    settlement = _settle(
        repo, code_repo, logger, write,
        f"## {FINDING}: declined\n- test: test_keeps_trailing_slash_on_redirect\n\n"
        "Reason: Not a defect. The test drives the reported URL and passes.\n",
    )

    assert settlement.declined == [FINDING]
    assert settlement.open == []
    assert settlement.rejected == {}


def test_a_not_a_defect_decline_naming_a_test_no_repo_holds_comes_back_open(
    repo: Path, code_repo: Path, logger: logging.Logger, write: Callable[[Path, str], Path]
) -> None:
    settlement = _settle(
        repo, code_repo, logger, write,
        f"## {FINDING}: declined\n- test: test_nobody_wrote\n\nReason: not a defect.\n",
    )

    assert settlement.open == [FINDING]
    assert "test_nobody_wrote" in settlement.rejected[FINDING]


def test_a_decline_of_another_kind_settles_without_a_test(
    repo: Path, code_repo: Path, logger: logging.Logger, write: Callable[[Path, str], Path]
) -> None:
    settlement = _settle(
        repo, code_repo, logger, write,
        f"## {FINDING}: declined\nReason: the story's AC 4 asks for the redirect to keep the query string.\n",
    )

    assert settlement.declined == [FINDING]
    assert settlement.rejected == {}


def test_a_reuse_decline_without_a_coincidence_comes_back_open_with_the_coincidence_text(
    repo: Path, code_repo: Path, logger: logging.Logger, write: Callable[[Path, str], Path]
) -> None:
    settlement = _settle(
        repo, code_repo, logger, write,
        f"## {FINDING}: declined\nReason: improvement the slice does not need.\n",
        reuse=[FINDING],
    )

    assert settlement.declined == []
    assert settlement.open == [FINDING]
    assert 'open the reason with "coincidence:"' in settlement.rejected[FINDING]


def test_a_reuse_decline_naming_two_different_reasons_settles_as_declined(
    repo: Path, code_repo: Path, logger: logging.Logger, write: Callable[[Path, str], Path]
) -> None:
    settlement = _settle(
        repo, code_repo, logger, write,
        f"## {FINDING}: declined\nReason: coincidence: the public API's codes; the report's codes.\n",
        reuse=[FINDING],
    )

    assert settlement.declined == [FINDING]
    assert settlement.open == []


@pytest.mark.parametrize(
    "reason",
    ["coincidence: the public API's codes", "coincidence: the same codes; The Same Codes", "coincidence: ;"],
)
def test_a_reuse_decline_without_two_different_reasons_comes_back_open(
    repo: Path, code_repo: Path, logger: logging.Logger, write: Callable[[Path, str], Path], reason: str
) -> None:
    settlement = _settle(
        repo, code_repo, logger, write,
        f"## {FINDING}: declined\nReason: {reason}\n",
        reuse=[FINDING],
    )

    assert settlement.open == [FINDING]
    assert "coincidence" in settlement.rejected[FINDING]


def test_a_not_a_defect_decline_of_a_finding_that_is_not_reuse_still_follows_the_decline_rule(
    repo: Path, code_repo: Path, logger: logging.Logger, write: Callable[[Path, str], Path]
) -> None:
    settlement = _settle(
        repo, code_repo, logger, write,
        f"## {FINDING}: declined\nReason: not a defect. The redirect already keeps the slash.\n",
        reuse=["acme-story/review-1.9"],
    )

    assert "cites no test" in settlement.rejected[FINDING]


def test_the_coincidence_prefix_may_wear_markdown_and_any_case() -> None:
    assert coincidence_gap({"reason": "**Coincidence:** a; b"}) == ""
