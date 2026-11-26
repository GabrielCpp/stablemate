"""One state, one turn: hand `plan` to the agent and let its own tool-call loop run to completion inside it."""
from __future__ import annotations

from pydantic import BaseModel

from workhorse.cli import console_script
from workhorse.pyflow import Done, Registry, Workflow
from workhorse.runner.extract import parse_json_from_text

DRY_RUN_SUMMARY = "Dry run: plan not actually carried out."


class Outcome(BaseModel):
    """What the run reports once the plan is carried out."""

    summary: str


def outcome(reply: str | None) -> Outcome:
    """The reply's `summary` field when it carries one as JSON, else the reply's own text."""
    text = reply or DRY_RUN_SUMMARY
    parsed = parse_json_from_text(text, ["summary"])
    summary = parsed.get("summary") if parsed else None
    return Outcome(summary=summary if isinstance(summary, str) else text.strip())


class LoopRunner(Workflow):
    """A single state: run the plan, once, to completion."""

    plan: str = ""

    def start(self) -> Done:
        reply = outcome(self.agent("prompts/run.md", returns=str, args={"plan": self.plan}))
        self.logger.info("%s", reply.summary)
        return Done(reply)


workflow = (
    Registry("loop-runner", package=__package__)
    .add_blueprints()
    .stub_agents({"run": DRY_RUN_SUMMARY})
)

main = console_script(workflow.entry_point(LoopRunner))
