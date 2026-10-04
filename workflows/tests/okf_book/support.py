"""Paddock fixture apps, git helpers and a scripted agent keyed by prompt."""
from __future__ import annotations

import subprocess
from collections import Counter
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import override

from workhorse.context import WorkflowContext
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv
from workhorse.runner.backends.null import NullBackend
from workhorse.runner.ladder import AgentRunner
from workhorse.runner.spec import AgentNode

from workhorse_workflows.okf_book.main.lead_lap_flow import LEAD_PROMPT
from workhorse_workflows.okf_book.main.settle_repair_turn_flow import DESCRIBE_LABEL
from workhorse_workflows.okf_book.workflow import OkfBook

_drive: Callable[[OkfBook, RunEnv], object] = drive
LEAD_NODE = Path(LEAD_PROMPT).stem
FIX_COMMIT_NODE = "fix-refused-commit"


class StoppedAtTheGate(Exception):
    """The operator stopped the run at its gate, as `control stop` does, with the report the gate showed."""

    def __init__(self, report: object) -> None:
        super().__init__("the operator stopped the run at its gate")
        self.report = report


def driver(flow: OkfBook, env: RunEnv) -> object:
    """Drive the run to its end, or to the gate its operator stopped it at, and return what it ended on."""
    try:
        return _drive(flow, env)
    except StoppedAtTheGate as stopped:
        return stopped.report


APPS = Path(__file__).resolve().parents[3] / "paddock" / "data" / "apps"

Reply = Callable[[dict[str, object]], dict[str, object]]


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return done.stdout


def commits(repo: Path) -> list[str]:
    """Every commit subject, newest first."""
    return git(repo, "log", "--format=%s").splitlines()


def always(payload: dict[str, object]) -> Reply:
    """A reply that ignores the turn's arguments."""

    def _reply(_args: dict[str, object]) -> dict[str, object]:
        return payload

    return _reply


class ScriptedRunner(AgentRunner):
    """Answers each turn with the reply scripted for its prompt, and keeps every turn's arguments.

    A reply the turn's validator refuses is asked for once more, with the refusal under `refused` in its arguments, as the ladder asks again.
    A repair commit's describe turn that no test scripts gets the fixed description, and counts in `described` instead of the turns.
    A lead turn that no test scripts names nothing, so the run's own attribution stands, and counts in no turn.
    A turn sent to a refused commit that no test scripts changes nothing, so the refusal reaches the operator, and counts in no turn.
    """

    def __init__(self, replies: Mapping[str, Reply]) -> None:
        super().__init__(backend=NullBackend())
        self.replies: dict[str, Reply] = dict(replies)
        self.turns: Counter[str] = Counter()
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.nodes: list[AgentNode] = []
        self.refused: list[tuple[str, str]] = []
        self.described: list[dict[str, object]] = []

    @property
    def total(self) -> int:
        return sum(self.turns.values())

    def args_of(self, node: str) -> list[dict[str, object]]:
        return [args for name, args in self.calls if name == node]

    @override
    def run(
        self,
        node: AgentNode,
        context: WorkflowContext,
        workflow_dir: Path,
        session_id_path: Path | None = None,
        *,
        resume_session: bool = False,
        session_chain: str = "",
        run_dir: Path | None = None,
        visit_dir: Path | None = None,
        validate: Callable[[dict[str, object]], object] | None = None,
    ) -> tuple[str, dict[str, object]]:
        args = context.as_dict()
        if node.id == DESCRIBE_LABEL and node.id not in self.replies:
            self.described.append(args)
            return "scripted", {"description": f"repair pages of the {args['service']} book", "body": ""}
        if node.id == LEAD_NODE and node.id not in self.replies:
            return "scripted", {"findings": []}
        if node.id == FIX_COMMIT_NODE and node.id not in self.replies:
            return "scripted", {"fixed": ""}
        self.turns[node.id] += 1
        self.calls.append((node.id, args))
        self.nodes.append(node)
        reply = self.replies[node.id](args)
        if validate is None:
            return "scripted", reply
        try:
            _ = validate(reply)
        except ValueError as refusal:
            self.refused.append((node.id, str(refusal)))
            reply = self.replies[node.id]({**args, "refused": str(refusal)})
            _ = validate(reply)
        return "scripted", reply
