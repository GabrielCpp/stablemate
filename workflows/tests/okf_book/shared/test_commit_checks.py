"""A book commit meets the commit checks its repo declares, so a book that fails the repo's lint is refused with the finding."""
from __future__ import annotations

import json
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


def _check_listing(*checks: tuple[str, int]) -> str:
    return "".join(f"{sys.executable} -c 'import sys; sys.stderr.write({json.dumps(said)}); sys.exit({code})'\t5\n" for said, code in checks)


def _stage_a_page(root: Path) -> None:
    page = root / "docs/page.md"
    page.parent.mkdir(parents=True)
    _ = page.write_text("x\n", encoding="utf-8")


def test_two_failing_checks_out_of_three_are_both_returned_in_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = make_git_repo(tmp_path / "acme")
    _declares(monkeypatch, _check_listing(("first said no", 1), ("second is fine", 0), ("third said no", 2)), [])
    _stage_a_page(root)

    refusal = declared_checks_failure(root, "docs: page", ("docs",))

    assert refusal.count("refused the commit") == 2
    assert refusal.index("first said no") < refusal.index("third said no")
    assert "second is fine" not in refusal


def test_one_failing_check_returns_the_text_it_returned_before(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = make_git_repo(tmp_path / "acme")
    listing = _check_listing(("first is fine", 0), ("second said no", 1))
    _declares(monkeypatch, listing, [])
    _stage_a_page(root)

    refusal = declared_checks_failure(root, "docs: page", ("docs",))

    command = listing.splitlines()[1].partition("\t")[0]
    assert refusal == f"commit check `{command}` refused the commit:\nsecond said no"


def test_checks_that_all_pass_return_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = make_git_repo(tmp_path / "acme")
    _declares(monkeypatch, _check_listing(("one", 0), ("two", 0)), [])
    _stage_a_page(root)

    assert declared_checks_failure(root, "docs: page", ("docs",)) == ""
