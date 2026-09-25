"""The retry ledger: how many turns each file or page has failed, and why the last one failed.

A subject that fails `MAX_ATTEMPTS` turns is exhausted, and the phase that owns it blocks it.
An aggregation job carries its own ledger, with the tree as it stood before its first turn, and the defects and claims the check tallied then.
The nodes a judge cleared outlive the job, so a later job's judge rereads only text that changed since.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from workhorse_workflows.okf_book.shared.confine import Snapshot
from workhorse_workflows.okf_book.shared.jobs import Job
from workhorse_workflows.okf_book.shared.page_check import Tally

MAX_ATTEMPTS = 3
CLEARED_NAME = "cleared.json"


class FailureTally(BaseModel):
    """How many turns a file or page has failed, and why the last one failed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subject: str
    failures: int
    problems: tuple[str, ...]


def charge_failure(attempts: Iterable[FailureTally], subject: str, problems: Sequence[str]) -> tuple[FailureTally, ...]:
    """`attempts` with one more failure charged to `subject`."""
    kept = [a for a in attempts if a.subject != subject]
    before = next((a.failures for a in attempts if a.subject == subject), 0)
    return (*kept, FailureTally(subject=subject, failures=before + 1, problems=tuple(problems)))


def last_problems(attempts: Iterable[FailureTally], subject: str) -> tuple[str, ...]:
    return next((a.problems for a in attempts if a.subject == subject), ())


def exhausted(attempts: Iterable[FailureTally], subject: str) -> bool:
    return any(a.subject == subject and a.failures >= MAX_ATTEMPTS for a in attempts)


class ClearedNode(BaseModel):
    """A node a judge raised nothing against, at the text it judged, and the claims it found stated there."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    node: str
    digest: str
    claims: tuple[str, ...] = ()


class ClearedBook(BaseModel):
    """Every node a judge has cleared in the run so far, each at the text it was cleared at."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    nodes: tuple[ClearedNode, ...] = ()


def read_cleared(run_dir: Path) -> tuple[ClearedNode, ...]:
    path = run_dir / CLEARED_NAME
    if not path.is_file():
        return ()
    return ClearedBook.model_validate_json(path.read_text(encoding="utf-8")).nodes


def record_cleared(run_dir: Path, cleared: tuple[ClearedNode, ...]) -> None:
    """Keep `cleared` for later jobs. An entry for the same node replaces the one recorded before it."""
    merged = {entry.node: entry for entry in (*read_cleared(run_dir), *cleared)}
    run_dir.mkdir(parents=True, exist_ok=True)
    _ = (run_dir / CLEARED_NAME).write_text(ClearedBook(nodes=tuple(merged.values())).model_dump_json(indent=2), encoding="utf-8")


class JobLedger(BaseModel):
    """One aggregation job's attempt so far: the job, the tree, the inherited compile gaps and the check's tally before its first turn, each failed turn, and the nodes judged sound."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    job: Job
    before: Snapshot
    inherited_gaps: tuple[str, ...] = ()
    baseline: Tally = Tally()
    attempts: tuple[FailureTally, ...] = ()
    cleared: tuple[ClearedNode, ...] = ()

    @property
    def problems(self) -> tuple[str, ...]:
        return last_problems(self.attempts, self.job.subject)

    @property
    def exhausted(self) -> bool:
        return exhausted(self.attempts, self.job.subject)

    def charged(self, problems: Sequence[str]) -> JobLedger:
        return self.model_copy(update={"attempts": charge_failure(self.attempts, self.job.subject, problems)})

    def with_cleared(self, cleared: tuple[ClearedNode, ...]) -> JobLedger:
        return self.model_copy(update={"cleared": cleared})
