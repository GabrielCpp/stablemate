"""What the check a writing turn runs reads: the job's repo, service, pages, starting tree and inherited gaps, and beside them the output its runs spent."""
from __future__ import annotations

import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from workhorse_workflows.okf_book.shared.confine import Snapshot

CHECK_MODULE = f"{__package__}.check_pages"
JOB_CHECK_FILE = "job-check.json"
SPENT_FILE = "check-spent-tokens"


class JobCheck(BaseModel):
    """What the check after a job's turns compares against."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    root: Path
    service: str
    before: Snapshot
    owned_pages: tuple[str, ...] = ()
    inherited_gaps: tuple[str, ...] = ()


def job_check_path(run_dir: Path) -> Path:
    """Where the current job's check inputs are."""
    return run_dir / JOB_CHECK_FILE


def spent_path(check_path: Path) -> Path:
    """Where the problem tokens the runs of the check at `check_path` have printed are kept."""
    return check_path.with_name(SPENT_FILE)


def spent_tokens(check_path: Path) -> int:
    """The problem tokens the runs of the check at `check_path` have printed this turn."""
    path = spent_path(check_path)
    return int(path.read_text(encoding="utf-8")) if path.exists() else 0


def charge(check_path: Path, tokens: int) -> None:
    """Add `tokens` to what the runs of the check at `check_path` have printed this turn."""
    _ = spent_path(check_path).write_text(str(spent_tokens(check_path) + tokens), encoding="utf-8")


def write_job_check(run_dir: Path, check: JobCheck) -> Path:
    """Write the current job's check inputs with nothing spent yet, and return where they are."""
    path = job_check_path(run_dir)
    _ = path.write_text(check.model_dump_json(), encoding="utf-8")
    spent_path(path).unlink(missing_ok=True)
    return path


def check_command(run_dir: Path) -> str:
    """The command a writing turn runs, from any directory."""
    return f"{sys.executable} -m {CHECK_MODULE} {job_check_path(run_dir)}"
