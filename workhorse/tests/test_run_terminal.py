"""What status a finished run stamps on its telemetry, and why success was the one case that got it wrong."""
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
    """A one-state flow."""

    def start(self) -> Transition:
        return Done(None)


class _Registry(Registry):
    """A registry whose prompts directory is this `tests/` folder — see the same shim in test_run_budget.py."""

    def directory(self) -> Path:
        return Path(__file__).parent


def _build_registry() -> Registry:
    registry = _Registry("greeting")
    registry.add_flows(main=Greeting)
    registry.entry = Greeting
    return registry


REGISTRY = _build_registry()


class Recorder(otel._NullTelemetry):
    """Records the `end_run` calls in the order they arrive."""

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
    """A host that always builds `recorder`, with the collector probe and the test-process guard taken out of the picture — left real, the probe would answer from whatever is listening on the dev machine and these tests would pass or fail by environment."""
    return otel.TelemetryHost(
        settings=dataclasses.replace(otel.OtelSettings(), forced=True),
        build=lambda workflow, run_id, run_dir, settings: recorder,
    )


def _run(tmp: str, recorder: Recorder, failure: BaseException | None = None) -> int:
    """Drive a run that gets one transition in, then either returns or raises."""

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
    """The regression."""
    recorder = Recorder()
    with tempfile.TemporaryDirectory() as tmp:
        code = _run(tmp, recorder)

        assert code == 0, code
        assert recorder.ended, "a finished run reported no status at all"
        status, error = recorder.ended[0]
        assert status == "terminal", recorder.ended
        assert error is None, recorder.ended


def test_the_crash_backstop_still_fires_when_nothing_finalized():
    """The contrast that keeps the fix honest."""
    recorder = Recorder()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            code = _run(tmp, recorder, MemoryError("the node ate the machine"))
        except MemoryError:
            pass
        else:  # pragma: no cover — a swallowed crash is itself the failure
            raise AssertionError(f"the crash was swallowed, exit {code}")

    assert recorder.ended, "a crashed run reported no status at all"
    assert recorder.ended[0] == ("aborted", "run aborted before finalize"), recorder.ended


def test_a_workflow_failure_still_reports_fail_first():
    """The other finalizing branch, for the same reason: it returns from inside the `try`, so it must beat the backstop."""
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
