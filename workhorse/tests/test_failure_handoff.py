"""`WorkflowFailed` writes a diagnostic outbox entry before the process exits.

Every deliberate failure — driver-level or workflow-authored — lands on the same
`PyflowError` catch in `run_pyflow`. This is the one new capture that catch does: an
inbox message, `kind="failure"`, naming the failure class, the node the run stopped
at, and where its artifacts are — so a babysitting session (or a human) reads the
diagnosis straight from the run dir instead of only a line in a scrollback log.

Run: uv run python tests/test_failure_handoff.py   (or via pytest)
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

from workhorse import inbox, otel
from workhorse.pyflow import run as run_mod
from workhorse.pyflow.errors import RunBudgetExceeded, WorkflowFailed
from workhorse.pyflow.registry import Registry
from workhorse.pyflow.run import RunInvocation, run_pyflow
from workhorse.pyflow.transitions import Done, Transition
from workhorse.pyflow.workflow import Workflow


class Greeting(Workflow):
    """A one-state flow. `drive` is substituted in every test here — see the
    identical shim in test_run_terminal.py."""

    def start(self) -> Transition:
        return Done(None)


class _Registry(Registry):
    def directory(self) -> Path:
        return Path(__file__).parent


def _build_registry() -> Registry:
    registry = _Registry("greeting-handoff")
    registry.add_flows(main=Greeting)
    registry.entry = Greeting
    return registry


REGISTRY = _build_registry()


def _run(tmp: str, failure: BaseException, *, run_id: str = "t") -> tuple[int, Path]:
    """Drive a run that checkpoints one state, then raises `failure`.

    Returns the exit code and the run dir, so a test can inspect the outbox left
    behind without threading `writer` out of `run_pyflow` itself.
    """
    runs_dir = Path(tmp) / "runs"

    def fake_drive(wf: Any, env: Any, resume: Any = None) -> Any:
        env.writer.write_state_checkpoint("start", {}, inputs={}, flow="Greeting", ctx={})
        raise failure

    previous = otel.install(otel.TelemetryHost())
    try:
        with patch.object(run_mod, "drive", fake_drive):
            code = run_pyflow(RunInvocation(
                registry=REGISTRY, runs_dir=runs_dir, flow="main", run_id=run_id,
            ))
    finally:
        otel.install(previous)
    return code, runs_dir / f"greeting-handoff-{run_id}"


def test_a_workflow_failure_writes_a_diagnostic_outbox_entry():
    with tempfile.TemporaryDirectory() as tmp:
        code, run_dir = _run(tmp, WorkflowFailed("the story cannot be planned"))

        assert code == 1, code
        messages = inbox.all_messages(run_dir / "inbox.jsonl")
        assert len(messages) == 1, messages
        message = messages[0]
        assert (message.model_extra or {}).get("kind") == "failure", message
        assert "WorkflowFailed" in message.body, message.body
        assert "node: start" in message.body, message.body
        assert "the story cannot be planned" in message.body, message.body
        assert str(run_dir) in message.body, message.body
        assert not message.reply, "a fresh diagnosis is not yet answered"


def test_a_raise_sites_own_failure_class_and_artifacts_reach_the_outbox():
    """A raise site can attach a specific `failure_class` and artifact paths — see
    `WorkflowFailed.__init__` — and the handoff surfaces them instead of the bare
    exception class name."""
    with tempfile.TemporaryDirectory() as tmp:
        code, run_dir = _run(
            tmp,
            WorkflowFailed(
                "QA never passed for story 'widget'",
                failure_class="qa-give-up",
                artifacts={"qa": "/repo/specs/widget/qa.md"},
            ),
        )

        assert code == 1, code
        message = inbox.all_messages(run_dir / "inbox.jsonl")[0]
        assert "failure_class: qa-give-up" in message.body, message.body
        assert "qa: /repo/specs/widget/qa.md" in message.body, message.body


def test_a_run_budget_stop_writes_no_outbox_entry():
    """`RunBudgetExceeded` is an operational stop, not a verdict — see its own
    docstring. It returns before the diagnostic branch and leaves no `inbox.jsonl`,
    the same way it leaves the run dir un-terminaled."""
    with tempfile.TemporaryDirectory() as tmp:
        code, run_dir = _run(tmp, RunBudgetExceeded("out of wall clock"))

        assert code == 1, code
        assert not (run_dir / "inbox.jsonl").exists()


if __name__ == "__main__":
    test_a_workflow_failure_writes_a_diagnostic_outbox_entry()
    test_a_raise_sites_own_failure_class_and_artifacts_reach_the_outbox()
    test_a_run_budget_stop_writes_no_outbox_entry()
    print("ok")
