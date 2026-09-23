"""A writing turn checks its own pages with the same problems the check after the turn charges."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from workhorse_workflows.okf_book.budget import CHARS_PER_TOKEN, PROBLEM_TOKENS
from workhorse_workflows.okf_book.check_pages import (
    LEFT_OUT,
    MODULE,
    PASSED,
    USAGE,
    WAIVED_FILE,
    check_command,
    check_report,
    report_lines,
    write_waived,
)
from workhorse_workflows.okf_book.entries import FEATURES_DIR
from workhorse_workflows.okf_book.page_check import page_problems

App = Callable[[str], Path]
BOOK = f"{FEATURES_DIR}/tally"
ROOT_PAGE = f"{BOOK}/tally.md"
CONCEPT = f"{BOOK}/concepts/ledger-file.md"


def _waived(tmp_path: Path, gaps: tuple[str, ...] = ()) -> str:
    return str(write_waived(tmp_path, gaps))


def test_a_page_that_does_not_compile_prints_what_the_turn_would_be_charged(app: App, tmp_path: Path) -> None:
    repo = app("tally-cli")

    code, lines = check_report(repo, ["tally", _waived(tmp_path), ROOT_PAGE])

    assert code == 1
    assert lines == page_problems(repo, "tally", [ROOT_PAGE])
    assert all("does not compile" in line for line in lines)


def test_the_gaps_the_job_inherits_are_not_printed(app: App, tmp_path: Path) -> None:
    repo = app("tally-cli")
    inherited = page_problems(repo, "tally", [ROOT_PAGE])

    assert check_report(repo, ["tally", _waived(tmp_path, inherited), ROOT_PAGE]) == (0, (PASSED,))


def test_problems_past_the_budget_are_counted_not_printed() -> None:
    problems = tuple(f"{n:02d}" + "x" * (PROBLEM_TOKENS * CHARS_PER_TOKEN - 2) for n in range(20))

    code, lines = report_lines(problems)

    assert code == 1
    assert lines[:-1] == problems[: len(lines) - 1]
    assert lines[-1] == LEFT_OUT.format(count=len(problems) - len(lines) + 1)
    assert len(lines) < len(problems)


def test_a_page_named_from_the_repo_root_with_a_dot_passes(app: App, tmp_path: Path) -> None:
    assert check_report(app("tally-cli"), ["tally", _waived(tmp_path), f"./{CONCEPT}"]) == (0, (PASSED,))


def test_a_call_without_pages_prints_the_usage(app: App, tmp_path: Path) -> None:
    assert check_report(app("tally-cli"), ["tally", _waived(tmp_path)]) == (2, (USAGE,))


def test_the_command_names_the_module_the_service_and_the_waived_gaps(tmp_path: Path) -> None:
    assert check_command("tally", tmp_path / WAIVED_FILE).endswith(f" -m {MODULE} tally {tmp_path / WAIVED_FILE}")
