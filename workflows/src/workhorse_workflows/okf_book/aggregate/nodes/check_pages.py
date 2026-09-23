"""The check a writing turn runs on its pages before it replies. It prints what the check after the turn charges."""
from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from workhorse_workflows.okf_book.shared.budget import pack_problems
from workhorse_workflows.okf_book.shared.confine import Snapshot, book_changes, new_since_head
from workhorse_workflows.okf_book.shared.page_check import charged_pages, page_problems, unreached

MODULE = "workhorse_workflows.okf_book.aggregate.nodes.check_pages"
USAGE = f"usage: python -m {MODULE} <job-check.json>"
PASSED = "No problems. The check after your turn passes these pages."
LEFT_OUT = "{count} more problems are past this output's budget. Fix these and run it again."
JOB_CHECK_FILE = "job-check.json"
CHECK_RUNS = 3


class JobCheck(BaseModel):
    """What the check after a job's turns compares against: the repo, the job's service and pages, the tree before its first turn, and its inherited gaps."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    root: Path
    service: str
    before: Snapshot
    owned_pages: tuple[str, ...] = ()
    inherited_gaps: tuple[str, ...] = ()


def job_check_path(run_dir: Path) -> Path:
    """Where the current job's check inputs are."""
    return run_dir / JOB_CHECK_FILE


def write_job_check(run_dir: Path, check: JobCheck) -> Path:
    """Write the current job's check inputs, and return where they are."""
    path = job_check_path(run_dir)
    _ = path.write_text(check.model_dump_json(), encoding="utf-8")
    return path


def check_command(run_dir: Path) -> str:
    """The command a writing turn runs, from any directory."""
    return f"{sys.executable} -m {MODULE} {job_check_path(run_dir)}"


def job_problems(check: JobCheck) -> tuple[str, ...]:
    """Each new page nothing reaches, and each doctor error and compile gap on the job's own pages and the book pages changed since the job began."""
    root = check.root.resolve()
    changed = book_changes(root, check.service, check.before)
    dead = (page.rel for page in unreached(root, new_since_head(root, changed)))
    return (
        *(f"{page} is linked from no page the entries page reaches, so the check after your turn deletes it." for page in dead),
        *page_problems(root, check.service, charged_pages(root, changed, check.owned_pages), check.inherited_gaps),
    )


def report_lines(problems: Sequence[str]) -> tuple[int, tuple[str, ...]]:
    """The exit code and the lines to print for `problems`, packed as a writing turn is told them, with a count of the rest."""
    if not problems:
        return 0, (PASSED,)
    shown = pack_problems(problems)
    more = (LEFT_OUT.format(count=shown.left_out),)
    return 1, (*shown.kept, *(more if shown.left_out else ()))


def check_report(argv: Sequence[str]) -> tuple[int, tuple[str, ...]]:
    """The exit code and the lines to print for the job check file named in `argv`."""
    if len(argv) != 1:
        return 2, (USAGE,)
    check = JobCheck.model_validate_json(Path(argv[0]).read_text(encoding="utf-8"))
    return report_lines(job_problems(check))


def main() -> int:
    """Check the current job's pages."""
    code, lines = check_report(sys.argv[1:])
    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
