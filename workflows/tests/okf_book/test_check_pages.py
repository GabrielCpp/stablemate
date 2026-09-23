"""A writing turn checks its pages with the same problems the check after the turn charges."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from workhorse_workflows.okf_book.budget import CHARS_PER_TOKEN, PROBLEM_TOKENS
from workhorse_workflows.okf_book.check_pages import (
    LEFT_OUT,
    MODULE,
    PASSED,
    USAGE,
    JobCheck,
    check_command,
    check_report,
    job_check_path,
    report_lines,
    write_job_check,
)
from workhorse_workflows.okf_book.confine import snapshot
from workhorse_workflows.okf_book.entries import FEATURES_DIR, EntryLink, write_entries
from workhorse_workflows.okf_book.page_check import page_problems

App = Callable[[str], Path]
BOOK = f"{FEATURES_DIR}/tally"
ROOT_PAGE = f"{BOOK}/tally.md"
NEW_PAGE = f"{BOOK}/concepts/budget.md"


def _append(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    _ = path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")


def _report(repo: Path, run_dir: Path, inherited: tuple[str, ...] = ()) -> tuple[int, tuple[str, ...]]:
    return check_report(repo, [str(write_job_check(run_dir, JobCheck(service="tally", before=snapshot(repo), inherited_gaps=inherited)))])


def test_a_page_the_turn_only_added_to_is_checked(app: App, tmp_path: Path) -> None:
    repo = app("tally-cli")
    check = JobCheck(service="tally", before=snapshot(repo))
    _append(repo, ROOT_PAGE, "\nTally keeps a ledger.\n")

    code, lines = check_report(repo, [str(write_job_check(tmp_path, check))])

    assert code == 1
    assert lines == page_problems(repo, "tally", [ROOT_PAGE])
    assert all("does not compile" in line for line in lines)


def test_the_gaps_the_job_inherits_are_not_printed(app: App, tmp_path: Path) -> None:
    repo = app("tally-cli")
    inherited = page_problems(repo, "tally", [ROOT_PAGE])
    check = JobCheck(service="tally", before=snapshot(repo), inherited_gaps=inherited)
    _append(repo, ROOT_PAGE, "\nTally keeps a ledger.\n")

    assert check_report(repo, [str(write_job_check(tmp_path, check))]) == (0, (PASSED,))


def test_a_new_page_nothing_reaches_is_printed(app: App, tmp_path: Path) -> None:
    repo = app("tally-cli")
    _ = write_entries(repo, "tally", [EntryLink("Tally", "tally.md")])
    check = JobCheck(service="tally", before=snapshot(repo))
    _ = (repo / NEW_PAGE).write_text("---\ntype: concept\ntitle: Budget\n---\n# Budget\n\nA budget caps a trip.\n", encoding="utf-8")

    code, lines = check_report(repo, [str(write_job_check(tmp_path, check))])

    assert code == 1
    assert any(line.startswith(f"{NEW_PAGE} is linked from no page") for line in lines)


def test_a_job_that_changed_nothing_passes(app: App, tmp_path: Path) -> None:
    assert _report(app("tally-cli"), tmp_path) == (0, (PASSED,))


def test_problems_past_the_budget_are_counted_not_printed() -> None:
    problems = tuple(f"{n:02d}" + "x" * (PROBLEM_TOKENS * CHARS_PER_TOKEN - 2) for n in range(20))

    code, lines = report_lines(problems)

    assert code == 1
    assert lines[:-1] == problems[: len(lines) - 1]
    assert lines[-1] == LEFT_OUT.format(count=len(problems) - len(lines) + 1)
    assert len(lines) < len(problems)


def test_a_call_without_the_job_check_prints_the_usage(app: App) -> None:
    assert check_report(app("tally-cli"), []) == (2, (USAGE,))


def test_the_command_names_the_module_and_the_job_check(tmp_path: Path) -> None:
    assert check_command(tmp_path).endswith(f" -m {MODULE} {job_check_path(tmp_path)}")
