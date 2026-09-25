"""A scenario's result names each check that did not hold, with what it expected and what it observed."""

from __future__ import annotations

import json
from pathlib import Path

from ostler.qa.drivers import FailedCheck, PythonDriver
from ostler.qa.session import QaSession


def _driver(repo: Path) -> PythonDriver:
    spec = repo / "docs/specs/story-1"
    spec.mkdir(parents=True, exist_ok=True)
    (spec / "qa-okf-context.json").write_text(json.dumps({"featuresRoot": "docs/features"}), encoding="utf-8")
    session = QaSession.create(spec, "qa-failed-1", "story-1", {})
    return PythonDriver(session, "cli", {"driver": "cli"}, root=repo, variables={})


def _assert(label: str, *, passed: bool, expected: object, actual: object) -> dict[str, object]:
    return {"type": "assert", "id": label, "label": label, "passed": passed, "expected": expected, "actual": actual}


def test_a_failed_assert_is_named_on_the_result_with_what_it_expected_and_observed(repo: Path) -> None:
    records = [
        _assert("exit code", passed=True, expected=0, actual=0),
        _assert('created(subject="trip.csv")', passed=False, expected=True, actual=False),
        {"type": "scenario", "id": "s-1", "status": "failed", "assertions": 2, "failures": 1},
    ]

    result = _driver(repo)._grade("s-1", ["ac:1"], records, "", 0, timed_out=False)

    assert result.failed_checks == [FailedCheck('created(subject="trip.csv")', True, False)]


def test_a_scenario_whose_checks_all_hold_names_none(repo: Path) -> None:
    records = [
        _assert("exit code", passed=True, expected=0, actual=0),
        {"type": "scenario", "id": "s-1", "status": "passed", "assertions": 1, "failures": 0},
    ]

    result = _driver(repo)._grade("s-1", ["ac:1"], records, "", 0, timed_out=False)

    assert (result.status, result.failed_checks) == ("passed", [])
