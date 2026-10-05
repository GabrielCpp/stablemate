"""A run whose app stopped serving blocks at the next scenario, since every scenario after it would fail on the app's absence."""

from __future__ import annotations

from pathlib import Path

from ostler.qa.plan import load_plan
from ostler.qa.v2 import run_plan

from test_qa_runner import OBLIGATION, _plan, _records, _spec

STOPPED = "the app's server exited during the run"


def _run(tmp_path: Path, answers: list[str]) -> tuple[str, dict[str, object], Path]:
    spec = _spec(tmp_path)
    document, problems = load_plan(_plan(spec), spec, tmp_path)
    assert not problems and document is not None

    status, _message, summary = run_plan(document, root=tmp_path, stack_check=lambda: answers.pop(0))
    return status, summary, spec


def test_a_stack_that_stopped_blocks_the_run_and_leaves_its_claims_unreached(tmp_path: Path) -> None:
    status, summary, spec = _run(tmp_path, [STOPPED])

    assert status == "blocked"
    assert summary["runner_errors"] == [STOPPED]
    assert summary["verdicts"] == {OBLIGATION: "unreached"}
    assert not any(record["kind"] == "scenario_start" for record in _records(spec))


def test_a_stack_that_serves_lets_the_scenarios_run(tmp_path: Path) -> None:
    status, summary, _spec_dir = _run(tmp_path, [""])

    assert status == "passed"
    assert "runner_errors" not in summary
