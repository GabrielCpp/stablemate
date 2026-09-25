"""The check a writing turn runs on its pages before it replies. It prints what the check after the turn charges."""
from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from workhorse_workflows.okf_book.shared.budget import (
    CHECK_OUTPUT_BUDGET_TOKENS,
    PROBLEMS_BUDGET_TOKENS,
    pack_problems,
    total_text_tokens,
)
from workhorse_workflows.okf_book.aggregate.nodes.job_check import CHECK_MODULE, JobCheck, charge, spent_tokens
from workhorse_workflows.okf_book.shared.confine import book_changes, new_since_head
from workhorse_workflows.okf_book.shared.page_check import charged_pages, page_problems, unlinked_own_page_problems, unreached

USAGE = f"usage: python -m {CHECK_MODULE} <job-check.json>"
PASSED = (
    "No problems. The check after your turn passes these pages. Reply now. "
    "Nothing else is charged to this turn, and `ostler doctor` is not."
)
LEFT_OUT = "{count} more problems are past this output's budget. Fix these and run it again."
SPENT = (
    "{count} problems remain. Your runs have printed all the problem text this turn allows, "
    "so fix the problems earlier runs printed and run it again to see this count fall."
)


def job_problems(check: JobCheck) -> tuple[str, ...]:
    """Each new page and own page nothing reaches, and each doctor error and compile gap on the job's own pages and the book pages changed since the job began."""
    root = check.root.resolve()
    changed = book_changes(root, check.service, check.before)
    dead = (page.rel for page in unreached(root, new_since_head(root, changed)))
    return (
        *(f"{page} is linked from no page the entries page reaches, so the check after your turn deletes it." for page in dead),
        *unlinked_own_page_problems(root, check.owned_pages),
        *page_problems(root, check.service, charged_pages(root, changed, check.owned_pages), check.inherited_gaps),
    )


@dataclass(frozen=True, slots=True)
class Report:
    """The check's exit code and the lines it prints."""

    code: int
    lines: tuple[str, ...]

    @property
    def tokens(self) -> int:
        """What printing the report's lines costs the turn."""
        return total_text_tokens(self.lines)


LEFT_OUT_TOKENS = Report(1, (LEFT_OUT.format(count=10**6),)).tokens


def _fit_or_silence(report: Report, left_tokens: int) -> Report:
    return report if report.tokens <= left_tokens else Report(report.code, ())


def problem_report(problems: Sequence[str], left_tokens: int = PROBLEMS_BUDGET_TOKENS) -> Report:
    """The report on `problems`, never costing more than `left_tokens`, and keeping room for one count of what remains."""
    if not problems:
        return _fit_or_silence(Report(0, (PASSED,)), left_tokens)
    count_report = _fit_or_silence(Report(1, (SPENT.format(count=len(problems)),)), left_tokens)
    shown = pack_problems(problems, min(left_tokens - count_report.tokens, PROBLEMS_BUDGET_TOKENS) - LEFT_OUT_TOKENS)
    if not shown.kept:
        return count_report
    more = (LEFT_OUT.format(count=shown.left_out),)
    return Report(1, (*shown.kept, *(more if shown.left_out else ())))


def check_report(argv: Sequence[str]) -> Report:
    """The report on the job check file named in `argv`, within what its earlier runs left of the turn's output."""
    if len(argv) != 1:
        return Report(2, (USAGE,))
    path = Path(argv[0])
    check = JobCheck.model_validate_json(path.read_text(encoding="utf-8"))
    return problem_report(job_problems(check), CHECK_OUTPUT_BUDGET_TOKENS - spent_tokens(path))


def main() -> int:
    """Check the current job's pages, and charge every line the report prints to the turn."""
    argv = sys.argv[1:]
    report = check_report(argv)
    for line in report.lines:
        print(line)
    if len(argv) == 1:
        charge(Path(argv[0]), report.tokens)
    return report.code


if __name__ == "__main__":
    sys.exit(main())
