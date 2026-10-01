"""A scenario that stops records every claim it did not reach, and one failure saying what stopped it."""

from __future__ import annotations

import json
from pathlib import Path

from ostler.qa.attribution import Cause
from ostler.qa.drivers import PythonDriver, ScenarioResult
from ostler.qa.v2 import _run_verdicts
from ostler.qa.session import QaSession
from ostler.qa.verdict import Verdict, merged

CLAIMS = ["okf:docs/a.md#orders:does:1", "okf:docs/a.md#orders:does:2", "okf:docs/a.md#orders:does:3"]
GAP_FAULT = {"fault_class": "capability", "fixture": "payment-provider", "page": "docs/fixtures/payment-provider.md"}


def _driver(repo: Path) -> PythonDriver:
    spec = repo / "docs/specs/story-1"
    spec.mkdir(parents=True, exist_ok=True)
    (spec / "qa-okf-context.json").write_text(json.dumps({"featuresRoot": "docs/features"}), encoding="utf-8")
    session = QaSession.create(spec, "qa-unreached-1", "story-1", {})
    return PythonDriver(session, "cli", {"driver": "cli"}, root=repo, variables={})


def _assert(claim: str, *, passed: bool) -> dict[str, object]:
    return {"type": "assert", "id": claim, "label": claim, "passed": passed, "expected": 200, "actual": 200, "covers": [claim]}


def _stopped(status: int) -> dict[str, object]:
    exchange = {"method": "POST", "path": "/api/orders/7/lines", "status": status, "expected": None,
                "credential_sent": True, "precondition": ""}
    return {"type": "scenario", "id": "s-1", "status": "errored", "assertions": 1, "failures": 0,
            "error": "HttpError: POST returned 500", "stop": {"exchange": exchange}}


def test_the_claims_after_a_stop_are_unreached_and_the_one_before_keeps_its_verdict(repo: Path) -> None:
    result = _driver(repo)._grade("s-1", CLAIMS, [_assert(CLAIMS[0], passed=True), _stopped(500)], "", 1, timed_out=False)

    assert result.verdicts == {CLAIMS[0]: Verdict.PASS, CLAIMS[1]: Verdict.UNREACHED, CLAIMS[2]: Verdict.UNREACHED}
    assert result.unreached == CLAIMS[1:]


def test_a_stop_is_one_failure_attributed_from_the_request_that_stopped_it(repo: Path) -> None:
    result = _driver(repo)._grade("s-1", CLAIMS, [_assert(CLAIMS[0], passed=True), _stopped(500)], "", 1, timed_out=False)

    [check] = result.failed_checks
    assert (check.cause, check.status, check.shape, check.covers) == (Cause.APP, "500", "POST /api/…", tuple(CLAIMS[1:]))


def test_a_stop_after_a_recorded_failure_adds_nothing_when_every_claim_was_reached(repo: Path) -> None:
    records = [_assert(claim, passed=claim != CLAIMS[2]) for claim in CLAIMS] + [_stopped(409)]

    result = _driver(repo)._grade("s-1", CLAIMS, records, "", 1, timed_out=False)

    assert [check.label for check in result.failed_checks] == [CLAIMS[2]]
    assert result.verdicts[CLAIMS[2]] == Verdict.FAIL


def test_a_scenario_that_never_answered_leaves_its_claims_unreached_and_its_failure_unattributed(repo: Path) -> None:
    result = _driver(repo)._grade("s-1", CLAIMS, [], "", 1, timed_out=True)

    assert set(result.verdicts.values()) == {Verdict.UNREACHED}
    assert [check.cause for check in result.failed_checks] == [Cause.UNATTRIBUTED]


def test_a_finished_scenario_passes_the_claims_it_covers(repo: Path) -> None:
    records = [_assert(CLAIMS[0], passed=True), {"type": "scenario", "id": "s-1", "status": "passed", "assertions": 1, "failures": 0}]

    result = _driver(repo)._grade("s-1", CLAIMS, records, "", 0, timed_out=False)

    assert result.verdicts == dict.fromkeys(CLAIMS, Verdict.PASS)
    assert result.unreached == []


def test_a_claim_keeps_its_worst_verdict_across_scenarios() -> None:
    claim = CLAIMS[0]
    assert merged([{claim: Verdict.PASS}, {claim: Verdict.UNREACHED}]) == {claim: Verdict.UNREACHED}
    assert merged([{claim: Verdict.FAIL}, {claim: Verdict.UNREACHED}]) == {claim: Verdict.FAIL}
    assert merged([{claim: Verdict.FAIL}, {claim: Verdict.GAPPED}]) == {claim: Verdict.GAPPED}


def test_a_scenario_stopped_by_an_absent_capability_gaps_the_claims_it_did_not_reach(repo: Path) -> None:
    stopped = {"type": "scenario", "id": "s-1", "status": "errored", "assertions": 0, "failures": 0,
               "error": "RuntimeError: probe failed", "stop": {"fault": GAP_FAULT, "raised": "RuntimeError"}}

    result = _driver(repo)._grade("s-1", CLAIMS, [stopped], "", 1, timed_out=False)

    assert set(result.verdicts.values()) == {Verdict.GAPPED}
    [check] = result.failed_checks
    assert (check.cause, check.gap) == (Cause.ENVIRONMENT, "payment provider")


def test_a_check_failed_by_an_absent_capability_gaps_its_claim(repo: Path) -> None:
    failed = {**_assert(CLAIMS[0], passed=False), "fault": GAP_FAULT}
    records = [failed, {"type": "scenario", "id": "s-1", "status": "failed", "assertions": 1, "failures": 1}]

    result = _driver(repo)._grade("s-1", CLAIMS[:1], records, "", 1, timed_out=False)

    assert result.verdicts == {CLAIMS[0]: Verdict.GAPPED}


def test_a_run_gives_every_covered_claim_a_verdict_and_a_scenario_it_never_ran_leaves_its_claims_unreached() -> None:
    selected = [{"id": "s-1", "covers": CLAIMS[:2]}, {"id": "s-2", "covers": CLAIMS[2:]}]
    ran = {"s-1": ScenarioResult("failed", verdicts={CLAIMS[0]: Verdict.PASS, CLAIMS[1]: Verdict.FAIL})}

    assert _run_verdicts(selected, ran) == {CLAIMS[0]: "pass", CLAIMS[1]: "fail", CLAIMS[2]: "unreached"}
