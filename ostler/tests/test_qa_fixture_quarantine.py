"""A book fixture that failed to build in two scenarios holds back the rest that need it, and blames its own page for them."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ostler.qa.attribution import Attribution, Cause
from ostler.qa.drivers import FailedCheck, FixtureBuild, ScenarioResult
from ostler.qa.harness.ostler_qa import extract_fixtures
from ostler.qa.plan import load_plan
from ostler.qa.quarantine import FixtureQuarantine
from ostler.qa.v2 import run_plan

from conftest import write
from test_qa_runner import _records

SESSION = "docs/services/acme/fixtures/editor-session.md"
FIXTURE = """---
type: fixture
title: Editor session
---
# Editor session

- lifetime: scenario

## Steps

### sign-in

- kind: seed
- run: ./scripts/sign-in.sh
"""
HEADER = '''\
from ostler_qa import Qa, plan, scenario, target

plan(run_id="qa-run-1", story="story-1")

api = target("api")
'''
SCENARIO = '''

@scenario(target=api, mechanism="live", covers=["{obligation}"])
def scenario_{index}(qa: Qa) -> None:
    """Scenario {index}."""
    {body}
'''
SIGNED_IN = 'qa.fixture("editor-session")'


def _obligation(index: int) -> str:
    return f"okf:docs/services/acme/page-{index}.md:contract:{index}"


def _run(repo: Path, bodies: list[str], *, signs_in: bool, quarantine_after: int) -> tuple[dict[str, Any], Path]:
    write(repo / SESSION, FIXTURE)
    script = repo / "scripts/sign-in.sh"
    write(script, "#!/bin/sh\nexit 0\n" if signs_in else "#!/bin/sh\nexit 3\n")
    script.chmod(0o755)
    spec = repo / "docs/specs/story-1"
    spec.mkdir(parents=True, exist_ok=True)
    obligations = [_obligation(index) for index in range(len(bodies))]
    (spec / "qa-okf-context.json").write_text(json.dumps({
        "version": 1, "available": True, "servicesRoot": "docs/services", "contracts": [], "acceptanceCriteria": [],
        "healthFindings": [],
        "obligations": [{"id": claim, "kind": "contract", "node": "item", "source": claim.split(":")[1],
                         "requirement": "item is emitted", "evidenceRequired": "live", "reasons": []}
                        for claim in obligations],
        "bookFiles": [], "storyFile": None,
    }), encoding="utf-8")
    source = HEADER + "".join(SCENARIO.format(obligation=claim, index=index, body=body)
                              for index, (claim, body) in enumerate(zip(obligations, bodies, strict=True)))
    (spec / "qa_plan.py").write_text(source, encoding="utf-8")
    document, problems = load_plan(spec / "qa_plan.py", spec, repo)
    assert not problems and document is not None
    _status, _message, summary = run_plan(document, root=repo, quarantine_after=quarantine_after)
    return summary, spec


def test_a_fixture_that_failed_twice_holds_back_the_scenarios_after_it_and_blames_its_page(repo: Path) -> None:
    summary, spec = _run(repo, [SIGNED_IN, SIGNED_IN, "pass", SIGNED_IN, SIGNED_IN], signs_in=False, quarantine_after=2)

    started = [record["scenario"] for record in _records(spec) if record["kind"] == "scenario_start"]
    assert started == [f"scenario-{index}" for index in range(5)]
    assert not summary["scenarios"]["scenario-2"].get("message", "").startswith("not run")
    for held in ("scenario-3", "scenario-4"):
        scenario = summary["scenarios"][held]
        assert scenario["message"] == (
            "not run: fixture 'editor-session' failed to build in 2 scenarios (scenario-0, scenario-1) with no good "
            "build between them, the first observing line 11: qa.fixture(\"editor-session\"); RuntimeError: qa fixture 'editor-session' step 0 (seed) failed "
            "(exit 3: )")
        [check] = scenario["failed_checks"]
        assert (check["cause"], check["precondition"]) == ("arrangement", SESSION)
        assert summary["verdicts"][_obligation(int(held[-1]))] == "unreached"
    [quarantined] = [record for record in _records(spec) if record["kind"] == "fixture_quarantine"]
    assert quarantined["scenario"] == "scenario-1"


def test_without_a_threshold_every_scenario_builds_the_fixture_itself(repo: Path) -> None:
    summary, spec = _run(repo, [SIGNED_IN] * 3, signs_in=False, quarantine_after=0)

    assert all(not scenario.get("message", "").startswith("not run") for scenario in summary["scenarios"].values())
    assert not [record for record in _records(spec) if record["kind"] == "fixture_quarantine"]


def test_a_fixture_that_builds_holds_nothing_back(repo: Path) -> None:
    summary, _spec = _run(repo, [SIGNED_IN] * 3, signs_in=True, quarantine_after=1)

    assert all(not scenario.get("message", "").startswith("not run") for scenario in summary["scenarios"].values())


def _faulted(page: str = SESSION) -> ScenarioResult:
    check = FailedCheck.of("sign in", "built", "exit 3", attribution=Attribution(Cause.ARRANGEMENT, page))
    return ScenarioResult("failed", failures=1, aborted=True, failed_checks=[check])


def _needs(scenario_id: str, *fixtures: str) -> dict[str, Any]:
    return {"id": scenario_id, "covers": [], "fixtures": list(fixtures)}


def test_a_good_build_between_two_faults_starts_the_count_again() -> None:
    quarantine = FixtureQuarantine(2)
    built = ScenarioResult("passed", fixture_builds=[FixtureBuild("editor-session", SESSION, "scenario", 1.0)])

    assert quarantine.observe(_needs("a", "editor-session"), _faulted()) == ""
    assert quarantine.observe(_needs("b", "editor-session"), built) == ""
    assert quarantine.observe(_needs("c", "editor-session"), _faulted()) == ""

    assert quarantine.held(_needs("d", "editor-session")) is None


def test_a_quarantined_fixture_holds_back_only_the_scenarios_that_need_it() -> None:
    quarantine = FixtureQuarantine(2)
    _ = quarantine.observe(_needs("a", "editor-session"), _faulted())
    stopped = quarantine.observe(_needs("b", "editor-session"), _faulted())

    assert "fixture 'editor-session' failed to build in 2 scenarios (a, b)" in stopped
    assert quarantine.held(_needs("c", "seeded-acme")) is None
    assert quarantine.held(_needs("d", "seeded-acme", "editor-session")) is not None


def test_a_fault_in_a_fixture_the_scenario_does_not_call_is_not_counted_against_it() -> None:
    quarantine = FixtureQuarantine(1)

    _ = quarantine.observe(_needs("a", "editor-session"), _faulted("docs/services/acme/fixtures/test-stack.md"))

    assert quarantine.held(_needs("b", "editor-session")) is None


def test_the_plan_lists_the_fixtures_each_scenario_calls_once_each_and_skips_a_computed_name() -> None:
    source = HEADER + '''

@scenario(target=api, mechanism="live", covers=[])
def edits(qa: Qa) -> None:
    qa.fixture("editor-session")
    qa.fixture("document-open", "draft")
    qa.fixture("editor-session")
    qa.fixture(NAME)
'''

    assert extract_fixtures(source)["edits"] == ["editor-session", "document-open"]
