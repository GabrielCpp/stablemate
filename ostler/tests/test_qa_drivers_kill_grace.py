"""A scenario killed at its timeout is asked to stop before it is SIGKILLed, so what its children hold gets released."""

from __future__ import annotations

import os
import time
from pathlib import Path

from ostler.qa.drivers import LocalLauncher, PythonDriver
from ostler.qa.session import QaSession

from conftest import write

PLAN = '''\
from ostler_qa import Qa, plan, scenario, target
import os, subprocess, time

plan(run_id="qa-kill", story="kill")

api = target("api")


@scenario(target=api, mechanism="live", covers=["ac:1"])
def holds_a_releasable_child(qa: Qa) -> None:
    """Starts a child that lets go on SIGTERM, then outlives its timeout."""
    child = subprocess.Popen(["sh", "-c", 'trap "echo released > ' + os.environ["KILL_PROBE"] + '; exit 0" TERM; while true; do sleep 0.1; done'])
    time.sleep(60)


@scenario(target=api, mechanism="live", covers=["ac:2"])
def holds_a_stubborn_child(qa: Qa) -> None:
    """Starts a child that ignores SIGTERM, then outlives its timeout."""
    child = subprocess.Popen(["sh", "-c", 'trap "" TERM; echo $$ > ' + os.environ["KILL_PROBE"] + '; while true; do sleep 0.1; done'])
    time.sleep(60)
'''


def _run_past_timeout(repo: Path, scenario_id: str, probe: Path, grace: float) -> float:
    module = repo / "qa_plan.py"
    write(module, PLAN)
    spec = repo / "docs/specs/story-1"
    spec.mkdir(parents=True, exist_ok=True)
    session = QaSession.create(spec, "qa-kill-1", "story-1", {})
    launcher = LocalLauncher(kill_grace=grace)
    driver = PythonDriver(session, "api", {"driver": "python", "module": str(module)}, root=repo, variables={}, launcher=launcher)
    context = {"root": str(repo), "spec_dir": str(spec), "qa_dir": str(session.qa_dir)}
    os.environ["KILL_PROBE"] = str(probe)
    try:
        started = time.monotonic()
        _records, _output, _code, timed_out = launcher.execute(driver, scenario_id, 1.0, context)
    finally:
        del os.environ["KILL_PROBE"]
    assert timed_out
    return time.monotonic() - started


def test_a_child_that_lets_go_on_sigterm_gets_to_before_the_group_is_killed(repo: Path) -> None:
    probe = repo / "released.txt"
    _run_past_timeout(repo, "holds-a-releasable-child", probe, grace=5.0)
    assert probe.read_text().strip() == "released"


def test_a_child_that_ignores_sigterm_is_killed_once_the_grace_runs_out(repo: Path) -> None:
    probe = repo / "child.pid"
    elapsed = _run_past_timeout(repo, "holds-a-stubborn-child", probe, grace=1.0)
    pid = int(probe.read_text().strip())
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        raise AssertionError(f"child {pid} survived the SIGKILL")
    assert elapsed < 5.0
