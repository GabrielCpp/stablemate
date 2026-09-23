"""What the check a writing turn runs reads: the job's repo, service, pages, starting tree, inherited gaps and the output its runs spent."""
from __future__ import annotations

import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from workhorse_workflows.okf_book.shared.confine import Snapshot

CHECK_MODULE = f"{__package__}.check_pages"
JOB_CHECK_FILE = "job-check.json"


class JobCheck(BaseModel):
    """What the check after a job's turns compares against, and the problem tokens this turn's runs of it have printed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    root: Path
    service: str
    before: Snapshot
    owned_pages: tuple[str, ...] = ()
    inherited_gaps: tuple[str, ...] = ()
    spent_tokens: int = 0


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
    return f"{sys.executable} -m {CHECK_MODULE} {job_check_path(run_dir)}"
