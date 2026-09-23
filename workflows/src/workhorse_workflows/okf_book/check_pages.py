"""The check a writing turn runs on its own pages before it replies. It prints what the check after the turn charges."""
from __future__ import annotations

import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

from pydantic import TypeAdapter

from workhorse_workflows.okf_book.budget import pack_problems
from workhorse_workflows.okf_book.page_check import page_problems

MODULE = "workhorse_workflows.okf_book.check_pages"
USAGE = f"usage: python -m {MODULE} <service> <waived-gaps.json> <page>..."
PASSED = "No problems. The check after your turn passes these pages."
LEFT_OUT = "{count} more problems are past this output's budget. Fix these and run it again."
WAIVED_FILE = "waived-gaps.json"
CHECK_RUNS = 3
_WAIVED = TypeAdapter(tuple[str, ...])


def waived_path(run_dir: Path) -> Path:
    """Where the current job's waived gaps are."""
    return run_dir / WAIVED_FILE


def write_waived(run_dir: Path, gaps: Iterable[str]) -> Path:
    """Write the gaps the check after this job's turns does not charge, and return where they are."""
    path = waived_path(run_dir)
    _ = path.write_bytes(_WAIVED.dump_json(tuple(gaps)))
    return path


def check_command(service: str, waived: Path) -> str:
    """The command a writing turn runs from the repo root, with the pages it wrote after it."""
    return f"{sys.executable} -m {MODULE} {service} {waived}"


def _repo_relative(root: Path, page: str) -> str:
    path = (root / page).resolve()
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else page


def check_report(root: Path, argv: Sequence[str]) -> tuple[int, tuple[str, ...]]:
    """The exit code and the lines to print for the service, the waived gaps file and the pages in `argv`, checked under `root`."""
    if len(argv) < 3:
        return 2, (USAGE,)
    service, waived, *pages = argv
    resolved = root.resolve()
    inherited = _WAIVED.validate_json(Path(waived).read_bytes())
    return report_lines(page_problems(resolved, service, [_repo_relative(resolved, page) for page in pages], inherited))


def report_lines(problems: Sequence[str]) -> tuple[int, tuple[str, ...]]:
    """The exit code and the lines to print for `problems`, packed as a writing turn is told them, with a count of the rest."""
    if not problems:
        return 0, (PASSED,)
    shown = pack_problems(problems)
    more = (LEFT_OUT.format(count=shown.left_out),)
    return 1, (*shown.kept, *(more if shown.left_out else ()))


def main() -> int:
    """Check the pages named on the command line, from the current directory."""
    code, lines = check_report(Path.cwd(), sys.argv[1:])
    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
