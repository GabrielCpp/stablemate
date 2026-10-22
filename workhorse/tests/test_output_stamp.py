"""A node visit's output is stamped on its span, whichever way the node ran."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from _fakes import RecordingTelemetry
from workhorse import otel
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow import Blueprint, Done, Workflow
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv

Transition = Any


class Verdict(BaseModel):
    status: str = "?"
    findings: list[str] = []


class ScriptedRunner:
    def __init__(self, run: Any) -> None:
        self.run = run


bp = Blueprint("stamp")


@bp.node
def check(logger: Any) -> Verdict:
    return Verdict(status="checked", findings=["a", "b"])


def _env(tmp: str, **kwargs: Any) -> RunEnv:
    writer = ArtifactWriter("acme", Path(tmp) / "runs", run_id="t")
    return RunEnv(
        writer=writer,
        workflow_dir=Path(tmp),
        session_id_path=writer.run_dir / ".session_id",
        config=RunConfig(),
        **kwargs,
    )


def test_agent_call_and_handoff_visits_are_each_stamped_with_their_output():
    def fake_run(node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        return "rendered", {"status": "reviewed", "findings": ["x"]}

    class Child(Workflow):
        def start(self) -> Transition:
            return Done({"status": "child-done", "findings": [1, 2, 3]})

    class Parent(Workflow):
        def start(self) -> Transition:
            self.agent("prompts/review.md", returns=Verdict, args={})
            self.call(check)
            return Done(self.handoff(Child))

    fake = RecordingTelemetry()
    previous = otel.install(otel.TelemetryHost(active=fake))
    try:
        with tempfile.TemporaryDirectory() as tmp:
            env = _env(tmp, agent_runner=ScriptedRunner(fake_run))
            drive(Parent(), env)
    finally:
        otel.install(previous)

    stamped = {node: attrs for node, _, attrs in fake.stamps}
    assert stamped["review"]["workhorse.out.status"] == "reviewed"
    assert stamped["review"]["workhorse.out.findings.len"] == 1
    assert stamped["check"]["workhorse.out.status"] == "checked"
    assert stamped["check"]["workhorse.out.findings.len"] == 2
    assert stamped["child"]["workhorse.out.status"] == "child-done"
    assert stamped["child"]["workhorse.out.findings.len"] == 3


def test_a_stamp_uses_the_seq_of_the_visits_enter_event():
    class Flow(Workflow):
        def start(self) -> Transition:
            self.call(check)
            return Done("ok")

    fake = RecordingTelemetry()
    previous = otel.install(otel.TelemetryHost(active=fake))
    try:
        with tempfile.TemporaryDirectory() as tmp:
            env = _env(tmp)
            drive(Flow(), env)
            events = env.writer.read_events()
    finally:
        otel.install(previous)

    enter = next(e.seq for e in events if e.node == "check" and e.phase == "enter")
    assert [seq for node, seq, _ in fake.stamps if node == "check"] == [enter]
