"""What `WORKHORSE_MAX_RUNTIME_S` leaves behind, and why it must stay resumable.

The wall-clock budget is checked *between* states rather than enforced by killing the
process, and that choice only pays off if the run dir it leaves can actually be
continued. It could not: the budget raised a plain `WorkflowFailed`, every `PyflowError`
stamped `terminal="fail"`, and `rundir.find_latest_resumable` skips any run with a
terminal — so `--resume-latest` could not see the one kind of stop whose own error
message says "Raise the budget and resume". The workaround (`--resume-run <dir>`, which
never consults `terminal`) existed, which is exactly why the gap was quiet.

So the distinction under test is between a run that **decided** and a run that **stopped**:
a workflow reaching its fail terminal is over, and a clock running out is not.

Run: uv run python tests/test_run_budget.py   (or via pytest)
"""
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


class Budgeted(Workflow):
    """A one-state flow. It never runs — `drive` is substituted in every test here —
    but the registry needs a real entry class to resolve a directory and instantiate."""

    def start(self) -> Transition:
        return Done(None)


class _Registry(Registry):
    """A registry whose prompts directory is this `tests/` folder.

    `Registry.directory()` derives it from the package the entry class lives in, and a
    test module is not a package — so the real one raises here for a reason that has
    nothing to do with what is under test. Only the reference preflight reads it, and a
    directory with no `prompts/` has no references to resolve.
    """

    def directory(self) -> Path:
        return Path(__file__).parent


def _build_registry() -> Registry:
    registry = _Registry("budgeted")
    registry.add_flows(main=Budgeted)
    registry.entry = Budgeted
    return registry


#: Built once: a workflow class belongs to exactly one registry, and `add_flows` refuses
#: a second claim on `Budgeted` — so this cannot be per-test.
REGISTRY = _build_registry()


def _run(tmp: str, failure: BaseException) -> tuple[int, Path]:
    """Drive a run that gets one transition in and then fails with `failure`.

    The checkpoint write is part of the simulation, not scaffolding: the budget is
    checked once the loop has committed the position it is about to run, so a run that
    stops on it has already written a checkpoint — and `find_latest_resumable` requires
    one. A run that dies before its first transition has nothing to resume either way.
    """
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
        # No terminal — that field is the "this run is over" signal, and this run is not.
        assert record["terminal"] is None, record
        assert "out of clock" in (record["error"] or ""), record
        assert record["interrupted_at"], record
        assert find_latest_resumable(runs_dir) is not None


def test_a_workflow_that_fails_is_over_and_is_not_resumed():
    """The contrast that makes the test above mean something.

    Were the fix a blanket "never stamp a terminal on error", a workflow that reached its
    fail terminal would auto-resume into the state that just gave up and fail there
    again, forever. Only the budget stop changes.
    """
    with tempfile.TemporaryDirectory() as tmp:
        code, runs_dir = _run(tmp, WorkflowFailed("the story cannot be planned"))

        assert code == 1, code
        assert _record(runs_dir)["terminal"] == "fail", _record(runs_dir)
        assert find_latest_resumable(runs_dir) is None


def test_the_budget_error_is_not_a_workflow_failure():
    """`--dry-run` treats a `WorkflowFailed` as "walked into a declared fail terminal"
    and exits 0 for it. A budget stop is an operational fact about the machine running
    the smoke test, so it must not borrow that pass."""
    assert not issubclass(RunBudgetExceeded, WorkflowFailed)


def test_the_driver_raises_it_when_the_deadline_has_passed():
    """The other end of the wiring: the guard in `driver.drive` raises *this* class.

    Asserted through a real `drive` call with an already-expired deadline, because the
    fix is only as good as the raise site — the tests above substitute `drive`, so they
    would all still pass if the driver had gone on raising `WorkflowFailed`.
    """
    with tempfile.TemporaryDirectory() as tmp:
        writer = ArtifactWriter("budgeted", Path(tmp) / "runs", run_id="t")
        env = RunEnv(
            writer=writer,
            workflow_dir=Path(tmp),
            session_id_path=writer.run_dir / ".session_id",
            config=RunConfig(),
            deadline=0.0,  # the epoch: every clock reading is past it
        )
        try:
            drive(Budgeted(), env)
        except RunBudgetExceeded as exc:
            assert "WORKHORSE_MAX_RUNTIME_S" in str(exc), exc
        else:
            raise AssertionError("an expired deadline did not stop the run")


#: The clock `Handoff.start` burns and the driver reads — one instance, so the state can
#: spend time the run is measured against without reaching through the engine for it.
HANDOFF_CLOCK = FakeClock()


class Handoff(Workflow):
    """Two states, the first of which burns time and hands the second its findings.

    The shape of every gate in a real workflow: a state runs something slow, learns
    something, and passes what it learned as the next state's parameters.
    """

    def start(self) -> Transition:
        # A state that takes real time — the nine-minute agent turn, in fake seconds.
        HANDOFF_CLOCK.sleep(120)
        return Continue(None, self.settle, diagnostics=["ac:1 is not covered"])

    def settle(self, diagnostics: list[str] | None = None) -> Transition:
        return Done(diagnostics)


def test_the_findings_of_the_state_that_ran_survive_a_budget_stop():
    """A `Continue` reached on the last iteration must be on disk before the clock is read.

    State parameters *are* the checkpoint — that is the invariant `pyflow/workflow.py`
    opens with — but they only become durable when some iteration writes them, and the
    budget check used to run first. So a state that completed, produced findings, and then
    ran out of clock had them dropped: the resume replayed the state it had already run,
    with the arguments it held on *entry*.

    That is worse than the wasted pass it looks like. The replayed state is told the gate
    found nothing, so it reports nothing to fix. Observed in the link-shortener benchmark:
    `plan-qa` spent 8m57s, `validate_qa_plan` returned 24 diagnostics, the budget tripped on
    the transition carrying them, and the resumed turn answered "no changes needed" — then
    the *next* pass, handed the same diagnostics, fixed every one of them in a single turn.
    """
    with tempfile.TemporaryDirectory() as tmp:
        writer = ArtifactWriter("handoff", Path(tmp) / "runs", run_id="t")
        clock = HANDOFF_CLOCK
        env = RunEnv(
            writer=writer,
            workflow_dir=Path(tmp),
            session_id_path=writer.run_dir / ".session_id",
            config=RunConfig(),
            clock=clock,
            # Generous enough that `start` is entered, short enough that the 120s it
            # burns overruns it — the budget trips on the transition out of `start`.
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
