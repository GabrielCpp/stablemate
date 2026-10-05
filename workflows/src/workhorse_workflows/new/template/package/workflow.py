"""One agent turn and one check: the agent works until the check exits 0."""
from __future__ import annotations

import logging
import subprocess

from pydantic import BaseModel
from workhorse.cli import console_script
from workhorse.pyflow import Blueprint, Continue, Done, Registry, Workflow, WorkflowFailed, dry_run

OUTPUT_LIMIT = 12_000

blueprint = Blueprint("__WORKFLOW_NAME__")


@dry_run(summary="Dry run: no change made.")
class Fix(BaseModel):
    """What the agent turn must reply with once it has made its change."""

    summary: str


class CheckResult(BaseModel):
    """How one run of the check ended, and what it printed."""

    passed: bool
    exit_code: int
    output: str


def truncated(text: str, limit: int = OUTPUT_LIMIT) -> str:
    """The last `limit` characters of `text`, marked when anything was cut."""
    if len(text) <= limit:
        return text
    cut = len(text) - limit
    return f"[{cut} earlier characters cut]\n{text[-limit:]}"


@blueprint.node(stub=lambda _logger, *_a, **_kw: CheckResult(passed=True, exit_code=0, output=""))
def run_check(logger: logging.Logger, command: str, repo_dir: str = "") -> CheckResult:
    """Run the check command with a shell in the repo, and keep the tail of its output."""
    logger.info("running check: %s", command)
    done = subprocess.run(
        command,
        shell=True,
        cwd=repo_dir or None,
        capture_output=True,
        text=True,
        check=False,
    )
    output = truncated((done.stdout or "") + (done.stderr or ""))
    return CheckResult(passed=done.returncode == 0, exit_code=done.returncode, output=output)


class CheckLoop(Workflow):
    """Hand the task to the agent, run the check, and loop back with its output until it passes."""

    check: str = "__CHECK__"
    task: str = ""
    max_rounds: int = 5

    def start(self, attempt: int = 1, failure: str = "") -> Continue:
        """Run one agent turn, with the last failing check output when there is one."""
        reply = self.agent(
            "prompts/fix.md",
            returns=Fix,
            args={
                "check": self.check,
                "task": self.task,
                "failure": failure,
                "attempt": attempt,
                "max_rounds": self.max_rounds,
            },
            cwd=self.repo_dir or None,
        )
        self.logger.info("round %d: %s", attempt, reply.summary)
        return Continue(reply, self.verify, attempt=attempt).because("the agent finished its turn")

    def verify(self, attempt: int) -> Continue | Done:
        """Run the check: finish on exit 0, else go back to the agent with the output."""
        result = self.call(run_check, self.check, self.repo_dir)
        if result.passed:
            return Done(result).because(f"`{self.check}` exited 0 in round {attempt}")
        if attempt >= self.max_rounds:
            raise WorkflowFailed(
                f"`{self.check}` still exits {result.exit_code} after {attempt} rounds, "
                f"the max_rounds bound. Last output:\n{truncated(result.output, 2_000)}"
            )
        return Continue(result, self.start, attempt=attempt + 1, failure=result.output).because(
            f"`{self.check}` exited {result.exit_code} in round {attempt}"
        )


workflow = (
    Registry("__WORKFLOW_NAME__", package=__package__)
    .add_blueprints(blueprint)
)
main = console_script(workflow.entry_point(CheckLoop))
