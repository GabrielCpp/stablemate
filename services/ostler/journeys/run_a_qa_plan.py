from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from ..commands import Look
from ..fixtures import nothing
from ..graph import (CutFrames, LintBadPlan, LintPlan, ReadLedger, RecordAssertion, RecordStep, ReplayRun, ReportRun, RunBadPlan,
                     RunPlan, StartSession, StopSession, ValidateBadPlan, ValidatePlan)


class RunAQaPlan(Journey):
    """A reviewer checks a QA plan and runs it. They lint and validate a plan that is sound and one that is not, run
    both, read the report, the replay and the ledger before and after a run, find that nothing was recorded on video,
    then open a session by hand, record a step and an assertion, and close it."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            LintPlan(nothing()),
            LintBadPlan(nothing()),
            ValidatePlan(nothing()),
            ValidateBadPlan(nothing()),
            RunBadPlan(nothing()),
            ReportRun(nothing()),
            ReplayRun(nothing()),
            ReadLedger(nothing()),
            CutFrames(nothing()),
            Look(),
            RunPlan(nothing()),
            Look(),
            ReportRun(nothing()),
            ReplayRun(nothing()),
            ReadLedger(nothing()),
            CutFrames(nothing()),
            RecordStep(nothing()),
            RecordAssertion(nothing()),
            StartSession(nothing()),
            StartSession(nothing()),
            RecordStep(nothing()),
            Look(),
            RecordAssertion(nothing()),
            Look(),
            StopSession(nothing()),
            StopSession(nothing()),
            Look(),
        )
