"""The evidence gate's unsupported-Pass check — `_unsupported_pass_problems`.

`log_refs` is written by the assessor, and every other criterion check reads only what it
cites. So a criterion could name the four assertions of its scenario that passed, omit the
two that failed, and stand as a fully-proven Pass with no machine disagreeing — the exact
shape of a half-working feature shipping green. Observed on `02-page-identity`, where a
scenario's probe fixture was never written, two assertions failed on the missing file, and
the criterion still read Pass; only the auditor's prose caught it.

What is pinned here is that the run log, not the citation, decides: a scenario the runner
recorded a FAIL in cannot hold up a Pass, whether or not the refs admit the failure.
"""
from __future__ import annotations

import json
from pathlib import Path

from workhorse_workflows.coder.qa.nodes import evidence


def _spec_dir(tmp_path: Path, *records: dict) -> Path:
    log = tmp_path / "qa" / "qa-run.ndjson"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")
    return tmp_path


def _assert(scenario: str, ident: str, result: str) -> dict:
    return {"kind": "assert", "id": ident, "scenario": scenario, "result": result}


def _criterion(cid: str, verdict: str, *refs: str) -> dict:
    return {"id": cid, "kind": "behavioral", "verdict": verdict, "log_refs": list(refs)}


def test_a_pass_may_not_omit_its_scenarios_failures(tmp_path: Path) -> None:
    spec_dir = _spec_dir(
        tmp_path,
        _assert("ac3-reject-title-argument", "ac3-1-assert_contains", "PASS"),
        _assert("ac3-reject-title-argument", "ac3-2-assert_contains", "FAIL"),
        _assert("ac3-reject-title-argument", "ac3-3-assert_exit_code", "FAIL"),
    )
    criteria = [_criterion("ac:3", "Pass", "ac3-reject-title-argument:assert:1")]

    problems = evidence._unsupported_pass_problems(criteria, spec_dir)

    assert len(problems) == 1
    assert "ac:3: marked Pass but scenario `ac3-reject-title-argument` failed 2 assertion(s)" in (
        problems[0]
    )
    assert "ac3-2-assert_contains, ac3-3-assert_exit_code" in problems[0]


def test_a_pass_on_a_clean_scenario_is_left_alone(tmp_path: Path) -> None:
    spec_dir = _spec_dir(
        tmp_path,
        _assert("ac1-returns-uuid-format", "ac1-1-assert_contains", "PASS"),
        _assert("ac3-reject-title-argument", "ac3-2-assert_contains", "FAIL"),
    )
    criteria = [_criterion("ac:1", "Pass", "ac1-returns-uuid-format:assert:1")]

    assert evidence._unsupported_pass_problems(criteria, spec_dir) == []


def test_a_criterion_that_admits_the_failure_is_still_flagged(tmp_path: Path) -> None:
    """Citing the failed assertion does not license the Pass — `_criteria_problems` only
    checks that refs resolve, so honesty in the citation is not itself proof."""
    spec_dir = _spec_dir(
        tmp_path, _assert("ac3-reject-title-argument", "ac3-2-assert_contains", "FAIL")
    )
    criteria = [_criterion("ac:3", "Pass", "ac3-reject-title-argument:assert:2")]

    assert len(evidence._unsupported_pass_problems(criteria, spec_dir)) == 1


def test_a_failing_criterion_is_left_to_the_criteria_gate(tmp_path: Path) -> None:
    spec_dir = _spec_dir(
        tmp_path, _assert("ac3-reject-title-argument", "ac3-2-assert_contains", "FAIL")
    )
    criteria = [_criterion("ac:3", "Fail", "ac3-reject-title-argument:assert:2")]

    assert evidence._unsupported_pass_problems(criteria, spec_dir) == []


def test_no_run_log_leaves_the_check_silent(tmp_path: Path) -> None:
    """Absence of the log is `_artifact_problems`' finding to report, not this one's."""
    criteria = [_criterion("ac:1", "Pass", "ac1-returns-uuid-format:assert:1")]

    assert evidence._unsupported_pass_problems(criteria, tmp_path) == []
