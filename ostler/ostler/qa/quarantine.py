"""Hold back the scenarios that need a book fixture once that fixture has failed to build again and again in one run."""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ostler.qa.attribution import Attribution, Cause
from ostler.qa.drivers import FailedCheck, ScenarioResult
from ostler.qa.verdict import Verdict, judge

HELD_CAUSES = frozenset({Cause.ARRANGEMENT, Cause.ENVIRONMENT})


@dataclass(frozen=True, slots=True)
class Fault:
    """The first fault a fixture met since its last good build: whose fault it is and what it observed."""

    attribution: Attribution
    observed: str


@dataclass(slots=True)
class FixtureQuarantine:
    """The book fixtures a run has seen fail to build since their last good build, and the scenarios each one stopped."""

    threshold: int
    stopped: dict[str, list[str]] = field(default_factory=dict)
    faults: dict[str, Fault] = field(default_factory=dict)

    def held(self, scenario: Mapping[str, Any]) -> ScenarioResult | None:
        """The result a scenario gets without running, when a fixture it needs has failed to build in *threshold* scenarios since it last built."""
        if self.threshold <= 0:
            return None
        for name in _fixtures(scenario):
            stopped = self.stopped.get(name, [])
            if len(stopped) < self.threshold:
                continue
            return _held_result(scenario, name, stopped, self.faults[name])
        return None

    def observe(self, scenario: Mapping[str, Any], result: ScenarioResult) -> str:
        """Record which fixtures *result* built and which stopped it, and say so when this result puts a fixture in quarantine."""
        if self.threshold <= 0:
            return ""
        for build in result.fixture_builds:
            _ = self.stopped.pop(build.name, None)
            _ = self.faults.pop(build.name, None)
        needed = set(_fixtures(scenario))
        scenario_id = str(scenario.get("id", ""))
        quarantined = ""
        for name, fault in _fixture_faults(result).items():
            if name not in needed:
                continue
            stopped = self.stopped.setdefault(name, [])
            _ = self.faults.setdefault(name, fault)
            if scenario_id not in stopped:
                stopped.append(scenario_id)
            if len(stopped) == self.threshold:
                quarantined = f"{_failed(name, stopped)}, so the scenarios after them that need it do not run"
        return quarantined


def _failed(name: str, stopped: list[str]) -> str:
    return (f"fixture '{name}' failed to build in {len(stopped)} scenarios ({', '.join(stopped)}) "
            "with no good build between them")


def _fixtures(scenario: Mapping[str, Any]) -> list[str]:
    declared = scenario.get("fixtures")
    return [str(name) for name in declared] if isinstance(declared, list) else []


def _fixture_faults(result: ScenarioResult) -> dict[str, Fault]:
    """The fixtures whose fault stopped *result*, by name, each with the first check it failed."""
    faults: dict[str, Fault] = {}
    for check in result.failed_checks:
        if check.cause not in HELD_CAUSES or check.gap or not check.precondition:
            continue
        _ = faults.setdefault(Path(check.precondition).stem, Fault(check.attribution(), _last_line(check.actual)))
    return faults


def _last_line(actual: str) -> str:
    """The last line of what a check observed, which for a crashed scenario is the error under its traceback."""
    try:
        observed = json.loads(actual)
    except json.JSONDecodeError:
        observed = actual
    lines = [line.strip() for line in str(observed).splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _held_result(scenario: Mapping[str, Any], name: str, stopped: list[str], fault: Fault) -> ScenarioResult:
    covers = [str(claim) for claim in scenario.get("covers", [])]
    message = f"not run: {_failed(name, stopped)}, the first observing {fault.observed}"
    verdicts: dict[str, Verdict] = {}
    judge(verdicts, covers, Verdict.UNREACHED)
    check = FailedCheck.of(
        f"scenario '{scenario.get('id', '')}' was held back because fixture '{name}' does not build",
        f"fixture '{name}' builds",
        message,
        covers=covers,
        attribution=fault.attribution,
    )
    return ScenarioResult(
        status="failed", failures=1, aborted=True, message=message, failed_checks=[check],
        unreached=covers, verdicts=verdicts,
    )
