"""`code_changed` reads product paths: the book, the artifacts dir and tool output never count as a change."""
from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from workhorse_workflows.coder.shared.worktree import code_changed, snapshot_code_state


@pytest.fixture
def artifacts(repo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The artifacts dir inside the one repo, as the paddock layout puts it."""
    inside = repo / "artifacts"
    monkeypatch.setenv("STABLEMATE_ARTIFACTS_DIR", str(inside))
    return inside


def _snapshot(logger: logging.Logger, repo: Path) -> dict[str, str]:
    return snapshot_code_state(logger, repo_dir=str(repo)).status


def _changed(logger: logging.Logger, repo: Path, before: dict[str, str]) -> bool:
    return code_changed(logger, before=before, repo_dir=str(repo)).changed


def test_a_book_page_and_a_spec_file_do_not_count_as_a_code_change(
    repo: Path,
    artifacts: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
) -> None:
    before = _snapshot(logger, repo)

    write(repo / "docs" / "services" / "app" / "page.md", "# page\n")
    write(artifacts / "specs" / "STORY-1" / "qa_plan.py", "PLAN = 1\n")
    write(repo / "test-results" / "trace.zip", "bytes\n")

    assert _changed(logger, repo, before) is False


def test_an_edited_app_source_file_counts_as_a_code_change(
    repo: Path,
    artifacts: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
) -> None:
    before = _snapshot(logger, repo)

    write(repo / "src" / "app.py", "VALUE = 1\n")

    assert _changed(logger, repo, before) is True


def test_a_commit_of_a_source_file_counts_as_a_code_change(
    repo: Path,
    artifacts: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    before = _snapshot(logger, repo)

    write(repo / "src" / "app.py", "VALUE = 1\n")
    git(repo, "add", "src/app.py")
    git(repo, "commit", "-qm", "source")

    assert _changed(logger, repo, before) is True


def test_a_commit_of_only_the_book_is_not_a_code_change(
    repo: Path,
    artifacts: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    before = _snapshot(logger, repo)

    write(repo / "docs" / "services" / "app" / "page.md", "# page\n")
    git(repo, "add", "docs")
    git(repo, "commit", "-qm", "book")

    assert _changed(logger, repo, before) is False


def test_an_unreadable_snapshot_counts_as_a_code_change(
    repo: Path, artifacts: Path, logger: logging.Logger
) -> None:
    assert _changed(logger, repo, {}) is True
