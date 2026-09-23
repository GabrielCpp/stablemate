"""The retry ledger: how many turns each file or page has failed, and why the last one failed.

A subject that fails `MAX_ATTEMPTS` turns is exhausted, and the phase that owns it blocks it.
An aggregation job carries its own ledger, with the tree as it stood before its first turn.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence

from pydantic import BaseModel, ConfigDict

from workhorse_workflows.okf_book.confine import Snapshot
from workhorse_workflows.okf_book.jobs import Job

MAX_ATTEMPTS = 3


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


class JobLedger(BaseModel):
    """One aggregation job's attempt so far: the job, the tree and the inherited compile gaps before its first turn, and each failed turn."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    job: Job
    before: Snapshot
    inherited_gaps: tuple[str, ...] = ()
    attempts: tuple[FailureTally, ...] = ()

    @property
    def problems(self) -> tuple[str, ...]:
        return last_problems(self.attempts, self.job.subject)

    @property
    def exhausted(self) -> bool:
        return exhausted(self.attempts, self.job.subject)

    def charged(self, problems: Sequence[str]) -> JobLedger:
        return self.model_copy(update={"attempts": charge_failure(self.attempts, self.job.subject, problems)})
