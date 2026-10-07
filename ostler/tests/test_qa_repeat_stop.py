"""A run stops once one failure observation repeats across many scenarios on several pages, since one cause no page holds would fail every scenario after them the same way."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ostler.qa.drivers import FailedCheck, ScenarioResult
from ostler.qa.plan import load_plan
from ostler.qa.repeats import RepeatWatch, observation
from ostler.qa.v2 import run_plan

from test_qa_runner import _records

WALL = "waiting for get_by_role(\"button\", name=\"Save\")"
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


def _obligation(index: int, pages: int) -> str:
    return f"okf:docs/features/demo/page-{index % pages}.md:contract:{index}"


def _run(
    tmp_path: Path, bodies: list[str], *, pages: int, stop_on_repeat: int, only: list[str] | None = None,
) -> tuple[str, dict[str, Any], Path]:
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True, exist_ok=True)
    obligations = [_obligation(index, pages) for index in range(len(bodies))]
    (spec / "qa-okf-context.json").write_text(json.dumps({
        "version": 1, "available": True, "contracts": [], "acceptanceCriteria": [], "healthFindings": [],
        "obligations": [{"id": claim, "kind": "contract", "node": "item", "source": claim.split(":")[1],
                         "requirement": "item is emitted", "evidenceRequired": "live", "reasons": []}
                        for claim in obligations],
        "bookFiles": [], "storyFile": None,
    }), encoding="utf-8")
    source = HEADER + "".join(SCENARIO.format(obligation=claim, index=index, body=body)
                              for index, (claim, body) in enumerate(zip(obligations, bodies, strict=True)))
    (spec / "qa_plan.py").write_text(source, encoding="utf-8")
    document, problems = load_plan(spec / "qa_plan.py", spec, tmp_path)
    assert not problems and document is not None
    status, _message, summary = run_plan(document, root=tmp_path, stop_on_repeat=stop_on_repeat, only=only)
    return status, summary, spec


def _fails(note: str) -> str:
    return f"raise RuntimeError({note!r})"


def test_one_observation_on_many_pages_stops_the_run_and_leaves_the_rest_unreached(tmp_path: Path) -> None:
    status, summary, spec = _run(tmp_path, [_fails(WALL)] * 8, pages=3, stop_on_repeat=4)

    assert status == "failed"
    assert len(summary["scenarios"]) == 4
    stopped = summary["stopped_on_repeat"]
    assert WALL in stopped and "4 scenarios on 3 pages" in stopped
    assert summary["stopped_on_observation"] == f"RuntimeError: {WALL}"
    assert summary["verdicts"] == {_obligation(index, 3): "unreached" for index in range(8)}
    assert sum(record["kind"] == "scenario_start" for record in _records(spec)) == 4
    assert "runner_errors" not in summary


def test_an_observation_on_too_few_of_the_run_s_pages_lets_it_continue(tmp_path: Path) -> None:
    bodies = [_fails(WALL) if index % 4 < 2 else "pass" for index in range(8)]
    status, summary, _spec = _run(tmp_path, bodies, pages=4, stop_on_repeat=3)

    assert status == "failed"
    assert len(summary["scenarios"]) == 8
    assert "stopped_on_repeat" not in summary


def test_a_run_of_one_page_stops_on_a_repeat_on_that_page(tmp_path: Path) -> None:
    status, summary, _spec = _run(tmp_path, [_fails(WALL)] * 6, pages=1, stop_on_repeat=3)

    assert status == "failed"
    assert len(summary["scenarios"]) == 3
    stopped = summary["stopped_on_repeat"]
    assert "3 scenarios on 1 pages failed on one observation: " in stopped
    assert "outside any single page" not in stopped


def test_a_scoped_run_stops_on_a_repeat_on_one_of_its_pages(tmp_path: Path) -> None:
    bodies = [_fails(WALL) if index % 2 == 0 else "pass" for index in range(10)]
    status, summary, _spec = _run(
        tmp_path, bodies, pages=2, stop_on_repeat=3, only=[f"scenario-{index}" for index in range(10)])

    assert status == "failed"
    assert len(summary["scenarios"]) == 5
    stopped = summary["stopped_on_repeat"]
    assert "3 scenarios on 1 pages failed on one observation: " in stopped


def test_different_observations_do_not_add_up(tmp_path: Path) -> None:
    bodies = [_fails(f"missing control {chr(97 + index)}") for index in range(6)]
    _status, summary, _spec = _run(tmp_path, bodies, pages=3, stop_on_repeat=2)

    assert len(summary["scenarios"]) == 6
    assert "stopped_on_repeat" not in summary


def test_no_threshold_runs_every_scenario(tmp_path: Path) -> None:
    _status, summary, _spec = _run(tmp_path, [_fails(WALL)] * 5, pages=5, stop_on_repeat=0)

    assert len(summary["scenarios"]) == 5
    assert "stopped_on_repeat" not in summary


def test_an_observation_ignores_numbers_and_reads_the_last_line() -> None:
    first = ScenarioResult(status="failed", message="Traceback\n  line 12\nTimeout 5000ms exceeded\n")
    second = ScenarioResult(status="failed", message="Traceback\n  line 40\nTimeout 7000ms exceeded")

    assert observation(first) == observation(second) == "Timeout Nms exceeded"


def test_a_message_that_names_its_scenario_is_one_observation_with_its_last_problem() -> None:
    watch = RepeatWatch(3, 1)
    stops = [
        watch.observe(f"s{index}", [_obligation(index, 1)], ScenarioResult(
            status="failed",
            message=f"waiting for locator(\"#control-{chr(97 + index)}\"); scenario 's{index}' was photographed at '/login'"))
        for index in range(3)
    ]

    assert stops[:2] == ["", ""]
    assert "scenario '<scenario>' was photographed at '/login'" in stops[2]


def test_an_observation_without_a_message_is_the_first_check_observed() -> None:
    result = ScenarioResult(status="failed", failed_checks=[FailedCheck("status", "200", "401")])

    assert observation(result) == "N"


def test_a_gapped_failure_never_counts() -> None:
    watch = RepeatWatch(1)
    gapped = ScenarioResult(status="failed", message=WALL, failed_checks=[FailedCheck("probe", "0", "1", gap="payment provider")])

    assert not any(watch.observe(f"s{index}", [_obligation(index, 3)], gapped) for index in range(6))


def test_a_passed_scenario_never_counts() -> None:
    watch = RepeatWatch(1)

    assert not any(watch.observe(f"s{index}", [_obligation(index, 3)], ScenarioResult(status="passed")) for index in range(6))
