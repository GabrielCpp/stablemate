"""What status a finished run stamps on its telemetry, and why success was the one
case that got it wrong.

`run_pyflow` wraps the driver in a `try` whose `finally` stamps `aborted` — the
backstop for a process that dies before any branch finalizes. Every *failing* branch
returns from inside that `try`, so each one stamps its own status first and the
backstop finds the run already ended. The success path did not: it stamped `terminal`
on the far side of the `finally`, which by then had already written `aborted` with an
ERROR status.

Since `end_run` keeps the first status it is handed, that meant **every successful run
was recorded as an aborted crash** — nine days of a real collector held 63 finished
runs and not one `OK` span. The bug is invisible from inside a run (the console still
prints `done`) and invisible in any single test of `end_run` (which is correct on its
own); it lives entirely in the ordering of two call sites.

Run: uv run python tests/test_run_terminal.py   (or via pytest)
"""
from __future__ import annotations

import dataclasses
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

from workhorse import otel
from workhorse.pyflow import run as run_mod
from workhorse.pyflow.errors import WorkflowFailed
from workhorse.pyflow.registry import Registry
from workhorse.pyflow.run import RunInvocation, run_pyflow
from workhorse.pyflow.transitions import Done, Transition
from workhorse.pyflow.workflow import Workflow


class Greeting(Workflow):
    """A one-state flow. `drive` is substituted in every test here, so the body never
    runs — the registry only needs a real class to resolve a directory and instantiate."""

    def start(self) -> Transition:
        return Done(None)


class _Registry(Registry):
    """A registry whose prompts directory is this `tests/` folder — see the same
    shim in test_run_budget.py. A test module is not a package, so the real
    `directory()` raises for a reason unrelated to what is under test."""

    def directory(self) -> Path:
        return Path(__file__).parent


def _build_registry() -> Registry:
    registry = _Registry("greeting")
    registry.add_flows(main=Greeting)
    registry.entry = Greeting
    return registry


#: Built once — `add_flows` refuses a second claim on `Greeting`.
REGISTRY = _build_registry()


class Recorder(otel._NullTelemetry):
    """Records the `end_run` calls in the order they arrive.

    Subclassing the null adapter keeps this a real implementation of the port: only
    the two signals the tests read have a body, and everything else stays the no-op
    it is in production. It deliberately does **not** reimplement the first-wins rule
    — these tests assert the *order* of the calls, and that the real adapter keeps
    the first is asserted separately in test_otel.py. Splitting it that way means
    neither test can pass by re-encoding the other's assumption.
    """

    def __init__(self) -> None:
        self.ended: list[tuple[str, str | None]] = []

    def enabled(self) -> bool:
        return True

    def end_run(
        self,
        status: str,
        error: str | None = None,
        error_class: str = "",
        error_kind: str = "",
    ) -> None:
        self.ended.append((status, error))


def _host(recorder: Recorder) -> otel.TelemetryHost:
    """A host that always builds `recorder`, with the collector probe and the
    test-process guard taken out of the picture — left real, the probe would answer
    from whatever is listening on the dev machine and these tests would pass or fail
    by environment."""
    return otel.TelemetryHost(
        settings=dataclasses.replace(otel.OtelSettings(), forced=True),
        build=lambda workflow, run_id, run_dir, settings: recorder,
    )


def _run(tmp: str, recorder: Recorder, failure: BaseException | None = None) -> int:
    """Drive a run that gets one transition in, then either returns or raises.

    The recorder is passed in rather than returned, because the interesting case is
    the one where `run_pyflow` propagates: a returned value would be unreachable
    exactly when the crash backstop is what we came to assert.
    """

    def fake_drive(wf: Any, env: Any, resume: Any = None) -> Any:
        env.writer.write_state_checkpoint("start", {}, inputs={}, flow="Greeting", ctx={})
        if failure is not None:
            raise failure
        return None

    previous = otel.install(otel.TelemetryHost())
    try:
        with patch.object(run_mod, "drive", fake_drive):
            return run_pyflow(RunInvocation(
                registry=REGISTRY,
                runs_dir=Path(tmp) / "runs",
                flow="main",
                run_id="t",
                telemetry=_host(recorder),
            ))
    finally:
        otel.install(previous)


def test_a_successful_run_is_stamped_terminal_not_aborted():
    """The regression. `terminal` must be the *first* status the run reports, because
    the first is the one that is kept."""
    recorder = Recorder()
    with tempfile.TemporaryDirectory() as tmp:
        code = _run(tmp, recorder)

        assert code == 0, code
        assert recorder.ended, "a finished run reported no status at all"
        status, error = recorder.ended[0]
        assert status == "terminal", recorder.ended
        # …and it carries no error, or the root span is stamped ERROR anyway.
        assert error is None, recorder.ended


def test_the_crash_backstop_still_fires_when_nothing_finalized():
    """The contrast that keeps the fix honest.

    A fix of "delete the `finally`" would also make the test above pass, and would
    lose the case the backstop exists for: a run whose process dies on something no
    branch catches leaves the root span open and the run silently unfinished.
    """
    recorder = Recorder()
    with tempfile.TemporaryDirectory() as tmp:
        # Not a PyflowError and not a KeyboardInterrupt: nothing in run_pyflow
        # catches this, so the `finally` is the only thing left to stamp it.
        try:
            code = _run(tmp, recorder, MemoryError("the node ate the machine"))
        except MemoryError:
            pass  # It propagates, as it must — but the backstop ran on the way out.
        else:  # pragma: no cover — a swallowed crash is itself the failure
            raise AssertionError(f"the crash was swallowed, exit {code}")

    assert recorder.ended, "a crashed run reported no status at all"
    assert recorder.ended[0] == ("aborted", "run aborted before finalize"), recorder.ended


def test_a_workflow_failure_still_reports_fail_first():
    """The other finalizing branch, for the same reason: it returns from inside the
    `try`, so it must beat the backstop."""
    recorder = Recorder()
    with tempfile.TemporaryDirectory() as tmp:
        code = _run(tmp, recorder, WorkflowFailed("the story cannot be planned"))

        assert code == 1, code
        assert recorder.ended[0][0] == "fail", recorder.ended


if __name__ == "__main__":
    test_a_successful_run_is_stamped_terminal_not_aborted()
    test_the_crash_backstop_still_fires_when_nothing_finalized()
    test_a_workflow_failure_still_reports_fail_first()
    print("ok")
