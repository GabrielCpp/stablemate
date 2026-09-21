"""One state, one turn: hand `plan` to the agent and let its own tool-call loop run to completion inside it."""
from __future__ import annotations

from pydantic import BaseModel

from workhorse.cli import console_script
from workhorse.pyflow import Done, Registry, Workflow


class Outcome(BaseModel):
    """What the agent turn must reply with once the plan is carried out."""

    summary: str


class LoopRunner(Workflow):
    """A single state: run the plan, once, to completion."""

    plan: str = ""

    def start(self) -> Done:
        reply = self.agent(
            "prompts/run.md",
            returns=Outcome,
            args={"plan": self.plan},
        )
        self.logger.info("%s", reply.summary)
        return Done(reply)


workflow = (
    Registry("loop-runner", package=__package__)
    .add_blueprints()
    .stub_agents({"run": {"summary": "Dry run: plan not actually carried out."}})
)

main = console_script(workflow.entry_point(LoopRunner))
