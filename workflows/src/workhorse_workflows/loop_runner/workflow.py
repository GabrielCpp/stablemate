"""One state, one turn: hand `plan` to the agent and let its own tool-call loop run
to completion inside it.

There is no second state. A turn that finishes cleanly means the plan is done; a
turn that fails raises `WorkflowFailed`/`AgentTurnFailed` and the run ends failed —
that is the whole completion model (`Continue`/`Done`/raise are pyflow's only three
outcomes, and this workflow uses exactly one of the first two). No workflow-owned
turn cap either: whatever wall-clock or turn-count budget `self.agent` is given by
the run's own config is the only one that applies, same as any other workflow's turn.
"""
from __future__ import annotations

from pydantic import BaseModel

from workhorse.cli import console_script
from workhorse.pyflow import Done, Registry, Workflow


class Outcome(BaseModel):
    """What the agent turn must reply with once the plan is carried out."""

    summary: str


class LoopRunner(Workflow):
    """A single state: run the plan, once, to completion."""

    #: The work to do, verbatim — a groom dispatch queue item's params pass this
    #: straight through (`docs/plans/groom-dispatch-queue-and-loop-runner.md` §2.4).
    #: Not a structured "Plan" schema: this workflow imposes none, deliberately.
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
