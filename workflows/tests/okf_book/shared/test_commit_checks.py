"""A book commit meets the commit checks its repo declares, so a book that fails the repo's lint is refused with the finding."""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

import pytest

from workhorse.testing import make_git_repo
from workhorse_workflows.kit import commit_checks
from workhorse_workflows.kit.commit_checks import declared_checks_failure
from workhorse_workflows.okf_book.shared import book_flow
from workhorse_workflows.kit.tools import run_tool

SCRIPT = (
    Path(__file__).resolve().parents[4] / "base-library/library/policies/repo/python-lint/scripts/check_ruff_staged.py"
)


def _declares(monkeypatch: pytest.MonkeyPatch, listing: str, calls: list[list[str]]) -> None:
    def _run(argv: list[str], cwd: str | Path | None = None) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        if argv[:2] == ["farrier", "checks"]:
            return subprocess.CompletedProcess(argv, 0, stdout=listing, stderr="")
        return run_tool(argv, cwd)

    monkeypatch.setattr(commit_checks, "run_tool", _run)


def _lint_listing() -> str:
    return f"{sys.executable} {SCRIPT}\t5\n"


def _head(root: Path) -> str:
    return subprocess.run(
        ["git", "log", "-1", "--format=%s"], cwd=str(root), capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def real_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(book_flow, "declared_checks_failure", declared_checks_failure)


def test_a_book_file_with_an_unused_import_is_refused_at_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, real_checks: None
) -> None:
    root = make_git_repo(tmp_path / "acme")
    _declares(monkeypatch, _lint_listing(), [])
    journey = root / "services/x/journeys/read.py"
    journey.parent.mkdir(parents=True)
    _ = journey.write_text("import os\n", encoding="utf-8")

    refusal = book_flow.commit_book_paths(logging.getLogger("test"), root, "docs(x): write the book", ("services/x",))

    assert "F401" in refusal
    assert "services/x/journeys/read.py:1:8" in refusal
    assert _head(root) == "init"


def test_a_book_file_that_passes_the_declared_checks_is_committed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, real_checks: None
) -> None:
    root = make_git_repo(tmp_path / "acme")
    _declares(monkeypatch, _lint_listing(), [])
    journey = root / "services/x/journeys/read.py"
    journey.parent.mkdir(parents=True)
    _ = journey.write_text("x = 1\n", encoding="utf-8")

    refusal = book_flow.commit_book_paths(logging.getLogger("test"), root, "docs(x): write the book", ("services/x",))

    assert (refusal, _head(root)) == ("", "docs(x): write the book")


def test_a_repo_that_declares_no_checks_commits_as_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, real_checks: None
) -> None:
    root = make_git_repo(tmp_path / "acme")
    calls: list[list[str]] = []
    _declares(monkeypatch, "", calls)
    page = root / "docs/page.md"
    page.parent.mkdir(parents=True)
    _ = page.write_text("x\n", encoding="utf-8")

    refusal = book_flow.commit_book_paths(logging.getLogger("test"), root, "docs: page", ("docs",))

    assert (refusal, _head(root), calls) == ("", "docs: page", [["farrier", "checks", "--repo", str(root)]])
