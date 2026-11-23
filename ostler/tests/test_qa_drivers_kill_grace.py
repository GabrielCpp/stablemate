"""A scenario killed at its timeout is asked to stop before it is SIGKILLed, so what its children hold gets released."""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

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


@pytest.fixture
def probe(repo: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    path = repo / "probe"
    monkeypatch.setenv("KILL_PROBE", str(path))
    yield path
    recorded = path.read_text().strip() if path.exists() else ""
    if recorded.isdigit():
        with contextlib.suppress(ProcessLookupError):
            os.kill(int(recorded), signal.SIGKILL)


def _gone(pid: int, within: float) -> bool:
    deadline = time.monotonic() + within
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


def _run_past_timeout(repo: Path, scenario_id: str, grace: float) -> float:
    module = repo / "qa_plan.py"
    write(module, PLAN)
    spec = repo / "docs/specs/story-1"
    spec.mkdir(parents=True, exist_ok=True)
    session = QaSession.create(spec, "qa-kill-1", "story-1", {})
    launcher = LocalLauncher(kill_grace=grace, session_store=repo / ".maestro" / "sessions")
    driver = PythonDriver(session, "api", {"driver": "python", "module": str(module)}, root=repo, variables={}, launcher=launcher)
    context = {"root": str(repo), "spec_dir": str(spec), "qa_dir": str(session.qa_dir)}
    started = time.monotonic()
    _records, _output, _code, timed_out = launcher.execute(driver, scenario_id, 1.0, context)
    assert timed_out
    return time.monotonic() - started


def test_a_child_that_lets_go_on_sigterm_gets_to_before_the_group_is_killed(repo: Path, probe: Path) -> None:
    _run_past_timeout(repo, "holds-a-releasable-child", grace=30.0)
    assert probe.read_text().strip() == "released"


def test_a_child_that_ignores_sigterm_is_killed_once_the_grace_runs_out(repo: Path, probe: Path) -> None:
    elapsed = _run_past_timeout(repo, "holds-a-stubborn-child", grace=1.0)
    pid = int(probe.read_text().strip())
    assert _gone(pid, within=30.0), f"child {pid} survived the SIGKILL"
    assert elapsed < 30.0


def test_an_interrupted_wait_reaps_the_scenario_group(repo: Path, probe: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = repo / "qa_plan.py"
    write(module, PLAN)
    spec = repo / "docs/specs/story-1"
    spec.mkdir(parents=True, exist_ok=True)
    session = QaSession.create(spec, "qa-kill-1", "story-1", {})
    launcher = LocalLauncher(kill_grace=1.0, session_store=repo / ".maestro" / "sessions")
    driver = PythonDriver(session, "api", {"driver": "python", "module": str(module)}, root=repo, variables={}, launcher=launcher)
    context = {"root": str(repo), "spec_dir": str(spec), "qa_dir": str(session.qa_dir)}
    real_communicate = subprocess.Popen.communicate
    calls = {"n": 0}

    def interrupted(self, input=None, timeout=None):
        if calls["n"] == 0:
            calls["n"] += 1
            pending = input
            deadline = time.monotonic() + 60
            while not probe.exists() and time.monotonic() < deadline:
                try:
                    real_communicate(self, pending, timeout=0.2)
                except subprocess.TimeoutExpired:
                    pending = None
            raise KeyboardInterrupt
        return real_communicate(self, input, timeout=timeout)

    monkeypatch.setattr(subprocess.Popen, "communicate", interrupted)
    with pytest.raises(KeyboardInterrupt):
        launcher.execute(driver, "holds-a-stubborn-child", 60.0, context)

    assert _gone(int(probe.read_text().strip()), within=30.0)
