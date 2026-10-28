"""A scenario is killed for going quiet past its timeout, not for running longer than it while its records keep arriving."""

from __future__ import annotations

import time
from pathlib import Path

from ostler.qa.drivers import LocalLauncher, PythonDriver
from ostler.qa.session import QaSession

from conftest import write

PLAN = '''\
from ostler_qa import Qa, plan, scenario, target
import time

plan(run_id="qa-stall", story="stall")

api = target("api")


@scenario(target=api, mechanism="live", covers=["ac:1"])
def keeps_reporting(qa: Qa) -> None:
    """Takes three times its timeout, and checks something every fraction of it."""
    for index in range(8):
        time.sleep(0.4)
        qa.check(f"step {index}", True)


@scenario(target=api, mechanism="live", covers=["ac:2"])
def goes_quiet_after_a_start(qa: Qa) -> None:
    """Checks once, then says nothing for longer than its timeout."""
    qa.check("started", True)
    time.sleep(60)
'''


def _execute(repo: Path, scenario_id: str, timeout: float) -> tuple[list[dict], int, bool, float]:
    module = repo / "qa_plan.py"
    write(module, PLAN)
    spec = repo / "docs/specs/story-1"
    spec.mkdir(parents=True, exist_ok=True)
    session = QaSession.create(spec, "qa-stall-1", "story-1", {})
    launcher = LocalLauncher(kill_grace=1.0, session_store=repo / ".maestro" / "sessions")
    driver = PythonDriver(session, "api", {"driver": "python", "module": str(module)}, root=repo, variables={}, launcher=launcher)
    context = {"root": str(repo), "spec_dir": str(spec), "qa_dir": str(session.qa_dir)}
    started = time.monotonic()
    records, _output, code, timed_out = launcher.execute(driver, scenario_id, timeout, context)
    return records, code, timed_out, time.monotonic() - started


def test_a_scenario_that_keeps_reporting_outlives_its_timeout(repo: Path) -> None:
    records, code, timed_out, _elapsed = _execute(repo, "keeps-reporting", 1.0)

    assert (code, timed_out) == (0, False)
    assert records[-1]["status"] == "passed"


def test_a_scenario_that_goes_quiet_is_killed_one_timeout_after_its_last_record(repo: Path) -> None:
    records, _code, timed_out, elapsed = _execute(repo, "goes-quiet-after-a-start", 1.0)

    assert timed_out
    assert [record["type"] for record in records][:1] == ["assert"]
    assert elapsed < 10.0
