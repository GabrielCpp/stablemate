from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from ..commands import Look
from ..fixtures import nothing
from ..graph import (EnvUpUnknown, RunGrpcPlan, RunPhonePlan, RunWebPlan, ValidatePhonePlan, ValidateWebPlan, VetDryRun,
                     VetOfUnknownStory, VetWithoutArguments, VetWithoutRegions)


class TryWhatTheSandboxLacks(Journey):
    """A reviewer reaches for what a text sandbox does not hold. They validate a plan for a browser and one for a phone,
    try to run both and find the run blocked on a secret before anything starts, run a plan that calls a gRPC service
    nobody serves and see it fail, bring up a book with no stack, and ask the visual check for nothing, for a regions
    file that is not there, for a story that does not exist, and for a clean dry run."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            ValidateWebPlan(nothing()),
            ValidatePhonePlan(nothing()),
            RunWebPlan(nothing()),
            RunPhonePlan(nothing()),
            RunGrpcPlan(nothing()),
            EnvUpUnknown(nothing()),
            VetWithoutArguments(nothing()),
            VetWithoutRegions(nothing()),
            VetOfUnknownStory(nothing()),
            VetDryRun(nothing()),
            Look(),
        )
