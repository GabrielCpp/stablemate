"""Which side each failed scenario of a scored run sits on, read from the cause ostler gave its failed checks."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ostler.qa.attribution import Cause

from workhorse_workflows.coder.shared.failed import failed_scenario_ids
from workhorse_workflows.kit.qa.schemas import QaPlanRun

PRECEDENCE = (Cause.ENVIRONMENT, Cause.ARRANGEMENT, Cause.BOOK, Cause.APP)


@dataclass(frozen=True)
class FailedScenario:
    """One failed scenario, the side it sits on, and the checks ostler recorded failing in it."""

    id: str
    cause: Cause
    checks: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True)
class RunSides:
    """A failed run's scenarios, split by the owner each side goes to."""

    environment: tuple[FailedScenario, ...] = ()
    book: tuple[FailedScenario, ...] = ()
    product: tuple[FailedScenario, ...] = ()
    unattributed: tuple[FailedScenario, ...] = ()


def _cause(check: Mapping[str, Any]) -> Cause:
    try:
        return Cause(str(check.get("cause", "")))
    except ValueError:
        return Cause.UNATTRIBUTED


def scenario_cause(checks: tuple[Mapping[str, Any], ...]) -> Cause:
    """The side of one failed scenario: the first of environment, arrangement, book and product that any of its checks names, else unattributed."""
    named = {_cause(check) for check in checks}
    return next((cause for cause in PRECEDENCE if cause in named), Cause.UNATTRIBUTED)


def _checks(outcome: Any) -> tuple[Mapping[str, Any], ...]:
    checks: Any = outcome.get("failed_checks") if isinstance(outcome, Mapping) else None
    if not isinstance(checks, list):
        return ()
    return tuple(check for check in checks if isinstance(check, Mapping))


def run_sides(run: QaPlanRun) -> RunSides:
    """Every scenario a failed run did not pass, on the side its failed checks name."""
    scenarios = run.ostler.get("scenarios")
    outcomes: Mapping[str, Any] = scenarios if isinstance(scenarios, Mapping) else {}
    failed = [
        FailedScenario(sid, scenario_cause(checks), checks)
        for sid in failed_scenario_ids(run)
        for checks in (_checks(outcomes.get(sid)),)
    ]
    return RunSides(
        environment=tuple(s for s in failed if s.cause is Cause.ENVIRONMENT),
        book=tuple(s for s in failed if s.cause in (Cause.BOOK, Cause.ARRANGEMENT)),
        product=tuple(s for s in failed if s.cause is Cause.APP),
        unattributed=tuple(s for s in failed if s.cause is Cause.UNATTRIBUTED),
    )


__all__ = ["FailedScenario", "RunSides", "run_sides", "scenario_cause"]
