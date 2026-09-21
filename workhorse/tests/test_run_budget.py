"""What `WORKHORSE_MAX_RUNTIME_S` leaves behind, and why it must stay resumable."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

from _fakes import FakeClock
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow import run as run_mod
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv
from workhorse.pyflow.errors import RunBudgetExceeded, WorkflowFailed
from workhorse.pyflow.registry import Registry
from workhorse.pyflow.run import RunInvocation, run_pyflow
from workhorse.pyflow.transitions import Continue, Done, Transition
from workhorse.pyflow.workflow import Workflow
from workhorse.rundir import find_latest_resumable
from workhorse.runner.failure import BackendInvocationError


class Budgeted(Workflow):
    """A one-state flow."""

    def start(self) -> Transition:
        return Done(None)


class _Registry(Registry):
    """A registry whose prompts directory is this `tests/` folder."""

    def directory(self) -> Path:
        return Path(__file__).parent


def _build_registry() -> Registry:
    registry = _Registry("budgeted")
    registry.add_flows(main=Budgeted)
    registry.entry = Budgeted
    return registry


REGISTRY = _build_registry()


def _run(tmp: str, failure: BaseException) -> tuple[int, Path]:
    """Drive a run that gets one transition in and then fails with `failure`."""
    runs_dir = Path(tmp) / "runs"

    def fake_drive(wf: Any, env: Any, resume: Any = None) -> Any:
        env.writer.write_state_checkpoint("start", {}, inputs={}, flow="Budgeted", ctx={})
        raise failure

    with patch.object(run_mod, "drive", fake_drive):
        code = run_pyflow(RunInvocation(
            registry=REGISTRY, runs_dir=runs_dir, flow="main", run_id="t",
        ))
    return code, runs_dir


def _record(runs_dir: Path) -> dict[str, Any]:
    (run_dir,) = [d for d in runs_dir.iterdir() if d.is_dir()]
    return json.loads((run_dir / "run.json").read_text())


def test_a_budget_stop_leaves_the_run_resumable():
    with tempfile.TemporaryDirectory() as tmp:
        code, runs_dir = _run(tmp, RunBudgetExceeded("out of clock"))

        assert code == 1, code
        record = _record(runs_dir)
        assert record["terminal"] is None, record
        assert "out of clock" in (record["error"] or ""), record
        assert record["interrupted_at"], record
        assert find_latest_resumable(runs_dir) is not None


def test_a_workflow_that_fails_is_over_and_is_not_resumed():
    """The contrast that makes the test above mean something."""
    with tempfile.TemporaryDirectory() as tmp:
        code, runs_dir = _run(tmp, WorkflowFailed("the story cannot be planned"))

        assert code == 1, code
        assert _record(runs_dir)["terminal"] == "fail", _record(runs_dir)
        assert find_latest_resumable(runs_dir) is None


def test_a_dead_agent_cli_stops_the_run_cleanly_and_resumably():
    """A `BackendInvocationError` past the ladder is the budget stop's sibling."""
    with tempfile.TemporaryDirectory() as tmp:
        code, runs_dir = _run(
            tmp, BackendInvocationError("agent CLI 'claude' could not be launched")
        )

        assert code == 1, code
        record = _record(runs_dir)
        assert record["terminal"] is None, record
        assert "could not be launched" in (record["error"] or ""), record
        assert find_latest_resumable(runs_dir) is not None


def test_a_resumable_stop_exports_interrupted_not_fail():
    """`run.json` keeping `terminal: null` for a budget stop or a dead CLI is only half of "resumable" — a fleet dashboard reads the *telemetry* export, not this file, and it classifies a run as dead off `workhorse.terminal`."""
    for failure in (
        RunBudgetExceeded("out of clock"),
        BackendInvocationError("agent CLI 'claude' could not be launched"),
    ):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(run_mod.otel, "end_run") as end_run:
                code, _ = _run(tmp, failure)
            assert code == 1, code
            first_status = end_run.call_args_list[0].args[0]
            assert first_status == "interrupted", (failure, first_status)


def test_the_budget_error_is_not_a_workflow_failure():
    """`--dry-run` treats a `WorkflowFailed` as "walked into a declared fail terminal" and exits 0 for it."""
    assert not issubclass(RunBudgetExceeded, WorkflowFailed)


def test_the_driver_raises_it_when_the_deadline_has_passed():
    """The other end of the wiring: the guard in `driver.drive` raises *this* class."""
    with tempfile.TemporaryDirectory() as tmp:
        writer = ArtifactWriter("budgeted", Path(tmp) / "runs", run_id="t")
        env = RunEnv(
            writer=writer,
            workflow_dir=Path(tmp),
            session_id_path=writer.run_dir / ".session_id",
            config=RunConfig(),
            deadline=0.0,
        )
        try:
            drive(Budgeted(), env)
        except RunBudgetExceeded as exc:
            assert "WORKHORSE_MAX_RUNTIME_S" in str(exc), exc
        else:
            raise AssertionError("an expired deadline did not stop the run")


HANDOFF_CLOCK = FakeClock()


class Handoff(Workflow):
    """Two states, the first of which burns time and hands the second its findings."""

    def start(self) -> Transition:
        HANDOFF_CLOCK.sleep(120)
        return Continue(None, self.settle, diagnostics=["ac:1 is not covered"])

    def settle(self, diagnostics: list[str] | None = None) -> Transition:
        return Done(diagnostics)


def test_the_findings_of_the_state_that_ran_survive_a_budget_stop():
    """A `Continue` reached on the last iteration must be on disk before the clock is read."""
    with tempfile.TemporaryDirectory() as tmp:
        writer = ArtifactWriter("handoff", Path(tmp) / "runs", run_id="t")
        clock = HANDOFF_CLOCK
        env = RunEnv(
            writer=writer,
            workflow_dir=Path(tmp),
            session_id_path=writer.run_dir / ".session_id",
            config=RunConfig(),
            clock=clock,
            deadline=clock.now().timestamp() + 60,
        )
        try:
            drive(Handoff(), env)
        except RunBudgetExceeded:
            pass
        else:
            raise AssertionError("a state that overran its budget did not stop the run")

        checkpoint = json.loads((writer.run_dir / "checkpoint.json").read_text())
        assert checkpoint["state"] == "settle", (
            f"resume would replay '{checkpoint['state']}', a state that already ran"
        )
        assert checkpoint["params"]["diagnostics"] == ["ac:1 is not covered"], (
            f"the findings did not survive the stop: {checkpoint['params']}"
        )


if __name__ == "__main__":
    for name, case in sorted(globals().items()):
        if name.startswith("test_") and callable(case):
            case()
            print(f"ok {name}")
    print("all good")
