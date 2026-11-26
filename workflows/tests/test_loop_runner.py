"""The loop runner takes the agent's reply as its summary, in whatever form the agent wrote it."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv
from workhorse.runner.backends.null import NullBackend
from workhorse.runner.ladder import AgentRunner
from workhorse_workflows.loop_runner.workflow import LoopRunner, workflow


class _Replies(AgentRunner):
    """An agent whose turns answer with the given texts, in order."""

    def __init__(self, *texts: str) -> None:
        super().__init__(backend=NullBackend())
        self.texts = list(texts)
        self.prompts: list[str] = []

    def turn(self, prompt: str, node_id: str, session_id_path: Any, model: Any = None, **kwargs: Any) -> str:
        self.prompts.append(prompt)
        return self.texts.pop(0)


def _summary(agent: _Replies) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        writer = ArtifactWriter("loop-runner", Path(tmp) / "runs", run_id="t")
        env = RunEnv(
            writer=writer,
            workflow_dir=workflow.directory(),
            session_id_path=writer.run_dir / ".session_id",
            config=RunConfig(),
            agent_runner=agent,
        )
        return drive(LoopRunner(plan="Reply that 6+6 is 12."), env).summary


def test_a_plain_text_reply_is_the_summary_in_one_turn():
    agent = _Replies("6+6 is 12.", "unused")

    assert _summary(agent) == "6+6 is 12."
    assert len(agent.prompts) == 1


def test_a_json_reply_gives_its_summary_field():
    agent = _Replies('Done.\n```json\n{"summary": "6+6 is 12."}\n```')

    assert _summary(agent) == "6+6 is 12."
    assert len(agent.prompts) == 1
