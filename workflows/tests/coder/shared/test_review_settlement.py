"""A "not a defect" decline settles only behind a test that exists, and no other decline needs one."""
from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from ostler import Ostler
from workhorse_workflows.coder.shared import review
from workhorse_workflows.coder.shared.review import (
    ANSWERS_FILE,
    coincidence_gap,
    evidence_gap,
    settle_findings,
)

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
    spec_files: dict[str, str] | None = None,
    minted: list[str] | None = None,
):
    okf = Ostler(repo)
    assert okf.create_epic("acme-epic", "Acme epic").ok
    created = okf.create_story("acme-epic", "acme-story", "Acme story")
    assert created.ok
    if minted is not None:
        minted.append(created.entity_id)
    spec = Path(okf.spec_path(created.entity_id))
    write(spec / ANSWERS_FILE, answer)
    for name, text in (spec_files or {}).items():
        write(spec / name, text)
    return settle_findings(
        logger,
        story_slug="acme-story",
        story_id=created.entity_id,
        filed=[FINDING],
        repos=[str(code_repo)],
        repo_dir=str(repo),
        reuse=reuse,
    )


def test_the_settlement_commit_carries_the_storys_trailer(
    repo: Path,
    code_repo: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: list[tuple] = []
    minted: list[str] = []

    class Inside(Ostler):
        def spec_path(self, story: str) -> str:
            return str(repo / "specs" / story)

    monkeypatch.setattr(review, "Ostler", Inside)
    monkeypatch.setattr(
        review, "commit_paths", lambda root, message, *paths, **_kw: recorded.append((root, message, *paths)) or True
    )

    _settle(
        repo, code_repo, logger, write,
        f"## {FINDING}: declined\nReason: other kind.\n",
        minted=minted,
    )

    assert f"Story: {minted[0]}" in recorded[0][1]


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


def test_a_fixed_answer_citing_a_file_of_the_spec_folder_settles(
    repo: Path, code_repo: Path, logger: logging.Logger, write: Callable[[Path, str], Path]
) -> None:
    settlement = _settle(
        repo, code_repo, logger, write,
        f"## {FINDING}: fixed\n- path: plan.md\n",
        spec_files={"plan.md": "# Plan\n"},
    )

    assert settlement.settled == [FINDING]
    assert settlement.rejected == {}


@pytest.fixture
def spec_dir(tmp_path: Path, write: Callable[[Path, str], Path]) -> Path:
    folder = tmp_path / "specs" / "ACME-1"
    write(folder / "plan.md", "# Plan\n")
    write(folder / "qa" / "steps" / "perf" / "figures.json", "{}\n")
    (folder / "qa" / "empty").mkdir()
    write(tmp_path / "specs" / "other.md", "outside\n")
    return folder


def _gap(path: str, spec_dir: Path, changed: dict[str, list[str]] | None = None) -> str:
    return evidence_gap({"paths": [path]}, [], changed or {}, str(spec_dir))


@pytest.mark.parametrize(
    "spelling",
    ["plan.md", "./plan.md", "qa/steps/perf/figures.json", "specs/ACME-1/plan.md", "ACME-1/plan.md", "ABSOLUTE"],
)
def test_a_path_naming_an_existing_spec_file_holds(spec_dir: Path, spelling: str) -> None:
    cited = str(spec_dir / "plan.md") if spelling == "ABSOLUTE" else spelling

    assert _gap(cited, spec_dir) == ""


@pytest.mark.parametrize("cited", ["missing.md", "qa/empty", "qa", "../other.md", "specs/ACME-1/../other.md"])
def test_a_path_that_is_no_file_inside_the_spec_folder_does_not_hold(spec_dir: Path, cited: str) -> None:
    assert _gap(cited, spec_dir) == (
        f"path {cited} is not among the files this story changed in its code repos, "
        "and is no file of the story's spec folder"
    )


def test_a_spec_file_does_not_hold_without_a_spec_folder(spec_dir: Path) -> None:
    assert evidence_gap({"paths": [str(spec_dir / "plan.md")]}, [], {}) != ""


def test_a_changed_code_path_still_holds_with_a_spec_folder(spec_dir: Path, tmp_path: Path) -> None:
    changed = {str(tmp_path / "api-service"): ["src/app.py"]}

    assert _gap("src/app.py", spec_dir, changed) == ""
    assert _gap("src/other.py", spec_dir, changed) != ""
