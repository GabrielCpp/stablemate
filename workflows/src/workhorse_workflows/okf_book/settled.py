"""Which aggregation jobs the run is done with, and which queued job comes next.

A job is settled once its marker is written: committed when its pages went in, or put back when
it was abandoned. A resume reads the markers back, so it never takes up a settled job again.
"""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from workhorse_workflows.okf_book.jobs import Job, JobQueue

JOBS_DIR = "jobs"


class Settled(BaseModel):
    """A job the run is done with, and whether its pages were committed or put back."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    job: Job
    committed: bool


def settle_job(run_dir: Path, job: Job, *, committed: bool) -> None:
    folder = run_dir / JOBS_DIR
    folder.mkdir(parents=True, exist_ok=True)
    marker = Settled(job=job, committed=committed)
    _ = (folder / f"{job.key}.json").write_text(marker.model_dump_json(), encoding="utf-8")


def is_settled(run_dir: Path, job: Job) -> bool:
    return (run_dir / JOBS_DIR / f"{job.key}.json").is_file()


def settled_jobs(run_dir: Path) -> tuple[Settled, ...]:
    """Every job this run settled, committed or put back, by subject."""
    folder = run_dir / JOBS_DIR
    if not folder.is_dir():
        return ()
    found = (Settled.model_validate_json(path.read_text(encoding="utf-8")) for path in folder.glob("*.json"))
    return tuple(sorted(found, key=lambda settled: settled.job.subject))


def committed_jobs(run_dir: Path) -> tuple[Job, ...]:
    """Every job whose pages this run committed, by subject. An abandoned job's pages were put back, so it is not among them."""
    return tuple(settled.job for settled in settled_jobs(run_dir) if settled.committed)


def next_job(run_dir: Path, queue: JobQueue, skip: Iterable[str] = ()) -> Job | None:
    """The first queued job not settled and not one of the `skip` subjects."""
    skipped = frozenset(skip)
    return next((job for job in queue.jobs if job.subject not in skipped and not is_settled(run_dir, job)), None)
