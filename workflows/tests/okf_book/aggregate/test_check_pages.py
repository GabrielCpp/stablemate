"""A writing turn checks its pages with the same problems the check after the turn charges."""
from __future__ import annotations

from collections.abc import Callable
import subprocess
import sys
from pathlib import Path

import pytest

from workhorse_workflows.okf_book.shared.budget import CHARS_PER_TOKEN, CHECK_OUTPUT_BUDGET_TOKENS, PROBLEM_TOKENS
from workhorse_workflows.okf_book.aggregate.nodes.check_pages import LEFT_OUT, PASSED, SPENT, USAGE, check_report, report_lines
from workhorse_workflows.okf_book.aggregate.nodes.job_check import (
    CHECK_MODULE,
    JobCheck,
    check_command,
    job_check_path,
    write_job_check,
)
from workhorse_workflows.okf_book.shared.confine import snapshot
from workhorse_workflows.okf_book.shared.entries import FEATURES_DIR, EntryLink, write_entries
from workhorse_workflows.okf_book.shared.page_check import page_problems

App = Callable[[str], Path]
BOOK = f"{FEATURES_DIR}/tally"
ROOT_PAGE = f"{BOOK}/tally.md"
NEW_PAGE = f"{BOOK}/concepts/budget.md"


def _append(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    _ = path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")


def _report(repo: Path, run_dir: Path, inherited: tuple[str, ...] = ()) -> tuple[int, tuple[str, ...]]:
    return check_report([str(write_job_check(run_dir, JobCheck(root=repo, service="tally", before=snapshot(repo), inherited_gaps=inherited)))])


def test_a_page_the_turn_only_added_to_is_checked(app: App, tmp_path: Path) -> None:
    repo = app("tally-cli")
    check = JobCheck(root=repo, service="tally", before=snapshot(repo))
    _append(repo, ROOT_PAGE, "\nTally keeps a ledger.\n")

    code, lines = check_report([str(write_job_check(tmp_path, check))])

    assert code == 1
    assert lines == page_problems(repo, "tally", [ROOT_PAGE])
    assert all("does not compile" in line for line in lines)


def test_a_page_the_job_owns_is_checked_before_the_turn_changes_it(app: App, tmp_path: Path) -> None:
    repo = app("tally-cli")
    check = JobCheck(root=repo, service="tally", before=snapshot(repo), owned_pages=(ROOT_PAGE,))

    code, lines = check_report([str(write_job_check(tmp_path, check))])

    assert code == 1
    assert lines == page_problems(repo, "tally", [ROOT_PAGE])


def test_the_gaps_the_job_inherits_are_not_printed(app: App, tmp_path: Path) -> None:
    repo = app("tally-cli")
    inherited = page_problems(repo, "tally", [ROOT_PAGE])
    check = JobCheck(root=repo, service="tally", before=snapshot(repo), inherited_gaps=inherited)
    _append(repo, ROOT_PAGE, "\nTally keeps a ledger.\n")

    assert check_report([str(write_job_check(tmp_path, check))]) == (0, (PASSED,))


def test_a_new_page_nothing_reaches_is_printed(app: App, tmp_path: Path) -> None:
    repo = app("tally-cli")
    _ = write_entries(repo, "tally", [EntryLink("Tally", "tally.md")])
    check = JobCheck(root=repo, service="tally", before=snapshot(repo))
    _ = (repo / NEW_PAGE).write_text("---\ntype: concept\ntitle: Budget\n---\n# Budget\n\nA budget caps a trip.\n", encoding="utf-8")

    code, lines = check_report([str(write_job_check(tmp_path, check))])

    assert code == 1
    assert any(line.startswith(f"{NEW_PAGE} is linked from no page") for line in lines)


def test_the_check_reads_the_job_repo_from_any_directory(app: App, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = app("tally-cli")
    check = JobCheck(root=repo, service="tally", before=snapshot(repo))
    _append(repo, ROOT_PAGE, "\nTally keeps a ledger.\n")
    path = write_job_check(tmp_path, check)
    monkeypatch.chdir(tmp_path)

    assert check_report([str(path)]) == (1, page_problems(repo, "tally", [ROOT_PAGE]))


def test_a_job_that_changed_nothing_passes(app: App, tmp_path: Path) -> None:
    assert _report(app("tally-cli"), tmp_path) == (0, (PASSED,))


def test_problems_past_the_budget_are_counted_not_printed() -> None:
    problems = tuple(f"{n:02d}" + "x" * (PROBLEM_TOKENS * CHARS_PER_TOKEN - 2) for n in range(20))

    code, lines, _ = report_lines(problems)

    assert code == 1
    assert lines[:-1] == problems[: len(lines) - 1]
    assert lines[-1] == LEFT_OUT.format(count=len(problems) - len(lines) + 1)
    assert len(lines) < len(problems)


def test_runs_past_the_turn_budget_print_only_the_count(app: App, tmp_path: Path) -> None:
    repo = app("tally-cli")
    check = JobCheck(root=repo, service="tally", before=snapshot(repo), spent_tokens=CHECK_OUTPUT_BUDGET_TOKENS)
    _append(repo, ROOT_PAGE, "\nTally keeps a ledger.\n")

    code, lines = check_report([str(write_job_check(tmp_path, check))])

    assert (code, lines) == (1, (SPENT.format(count=len(page_problems(repo, "tally", [ROOT_PAGE]))),))


def test_each_run_charges_what_it_printed(app: App, tmp_path: Path) -> None:
    repo = app("tally-cli")
    path = write_job_check(tmp_path, JobCheck(root=repo, service="tally", before=snapshot(repo)))
    _append(repo, ROOT_PAGE, "\nTally keeps a ledger.\n")
    _, _, printed = report_lines(page_problems(repo, "tally", [ROOT_PAGE]))

    _ = check_report([str(path)])
    _ = check_report([str(path)])

    assert JobCheck.model_validate_json(path.read_text(encoding="utf-8")).spent_tokens == 2 * printed


def test_a_call_without_the_job_check_prints_the_usage() -> None:
    assert check_report([]) == (2, (USAGE,))


def test_the_command_names_the_module_and_the_job_check(tmp_path: Path) -> None:
    assert check_command(tmp_path).endswith(f" -m {CHECK_MODULE} {job_check_path(tmp_path)}")


def test_the_command_prints_only_what_the_check_says(app: App, tmp_path: Path) -> None:
    repo = app("tally-cli")
    path = write_job_check(tmp_path, JobCheck(root=repo, service="tally", before=snapshot(repo)))

    ran = subprocess.run([sys.executable, "-m", CHECK_MODULE, str(path)], capture_output=True, text=True, check=False)

    assert (ran.returncode, ran.stdout, ran.stderr) == (0, f"{PASSED}\n", "")
