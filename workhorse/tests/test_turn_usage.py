"""An agent turn's usage is kept beside its output, whether the turn replied or failed."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from workhorse import otel
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow import AgentTurnFailed, Done, Workflow
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv
from workhorse.runner.failure import BackendInvocationError
from workhorse.runner.usage import TurnUsage, as_record, from_record

Transition = Any


class Payload(BaseModel):
    kind: str = "?"


class ScriptedRunner:
    def __init__(self, run: Any) -> None:
        self.run = run


def _env(tmp: str, **kwargs: Any) -> RunEnv:
    writer = ArtifactWriter("acme", Path(tmp) / "runs", run_id="t")
    return RunEnv(
        writer=writer,
        workflow_dir=Path(tmp),
        session_id_path=writer.run_dir / ".session_id",
        config=RunConfig(),
        **kwargs,
    )


def test_a_replying_turn_keeps_the_sum_of_its_usage_reports():
    with tempfile.TemporaryDirectory() as tmp:

        def reply(node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
            otel.turn_result(TurnUsage(output_tokens=5, total_cost_usd=0.25))
            otel.turn_result(TurnUsage(output_tokens=7, cache_read_input_tokens=100, total_cost_usd=0.5))
            return "rendered", {"kind": "ok"}

        env = _env(tmp, agent_runner=ScriptedRunner(reply))

        class Asks(Workflow):
            def start(self) -> Transition:
                self.agent("prompts/write.md", returns=Payload)
                return Done(as_record(self.turn_usage("write")))

        used = from_record(drive(Asks(), env))

        assert used == TurnUsage(output_tokens=12, cache_read_input_tokens=100, total_cost_usd=0.75)
        recorded = json.loads((env.run_dir / "write" / "usage.json").read_text())
        assert recorded["output_tokens"] == 12


def test_a_failed_turn_still_keeps_what_it_used():
    with tempfile.TemporaryDirectory() as tmp:

        def crash(node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
            otel.turn_result(TurnUsage(output_tokens=3, total_cost_usd=0.1))
            raise BackendInvocationError("the CLI exited with code 1", transient=False)

        env = _env(tmp, agent_runner=ScriptedRunner(crash))

        class Asks(Workflow):
            def start(self) -> Transition:
                try:
                    self.agent("prompts/write.md", returns=Payload)
                except AgentTurnFailed:
                    return Done(as_record(self.turn_usage("write")))
                return Done(None)

        assert from_record(drive(Asks(), env)) == TurnUsage(output_tokens=3, total_cost_usd=0.1)


def test_a_node_that_never_ran_used_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)

        class Asks(Workflow):
            def start(self) -> Transition:
                return Done(as_record(self.turn_usage("write")))

        assert from_record(drive(Asks(), env)) == TurnUsage()


def test_a_usage_report_outside_any_turn_reaches_no_tap():
    with otel.tapping_usage() as outer:
        with otel.tapping_usage() as inner:
            otel.turn_result(TurnUsage(output_tokens=1))
        otel.turn_result(TurnUsage(output_tokens=2))
    otel.turn_result(TurnUsage(output_tokens=4))

    assert inner == [TurnUsage(output_tokens=1)]
    assert outer == [TurnUsage(output_tokens=1), TurnUsage(output_tokens=2)]


def test_a_record_holding_no_usable_number_reports_nothing_under_it():
    record = {"output_tokens": "12", "input_tokens": 3.5, "cache_read_input_tokens": True, "steps": 4.0, "total_cost_usd": "0.2"}

    assert from_record(record) == TurnUsage(steps=4)
