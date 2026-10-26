"""Git helpers and a scripted agent keyed by prompt."""
from __future__ import annotations

import subprocess
from collections import Counter
from dataclasses import dataclass
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import override

from workhorse.context import WorkflowContext
from workhorse.runner.backends.null import NullBackend
from workhorse.runner.ladder import AgentRunner
from workhorse.runner.spec import AgentNode

FIX_COMMIT_NODE = "fix-refused-commit"

Reply = Callable[[dict[str, object]], dict[str, object]]

def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return done.stdout


class ScriptedRunner(AgentRunner):
    """Answers each turn with the reply scripted for its prompt, and keeps every turn's arguments.

    A reply the turn's validator refuses is asked for once more, with the refusal under `refused` in its arguments, as the ladder asks again.
    A turn sent to a refused commit that no test scripts changes nothing, so the refusal reaches the operator, and counts in no turn.
    """

    def __init__(self, replies: Mapping[str, Reply]) -> None:
        super().__init__(backend=NullBackend())
        self.replies: dict[str, Reply] = dict(replies)
        self.turns: Counter[str] = Counter()
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.nodes: list[AgentNode] = []
        self.refused: list[tuple[str, str]] = []
        self.chains: list[tuple[str, str]] = []
        self.resumed: list[bool] = []

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
        rebrief: Callable[[], str] | None = None,
    ) -> tuple[str, dict[str, object]]:
        args = context.as_dict()
        if node.id == FIX_COMMIT_NODE and node.id not in self.replies:
            return "scripted", {"fixed": ""}
        self.turns[node.id] += 1
        self.calls.append((node.id, args))
        self.nodes.append(node)
        self.chains.append((node.id, session_chain))
        if session_chain and session_id_path is not None:
            self.resumed.append(session_id_path.exists())
            session_id_path.parent.mkdir(parents=True, exist_ok=True)
            _ = session_id_path.write_text(f"session-{self.total}", encoding="utf-8")
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


MEMBER = "api-service"
MEMBER_FOLDER = "api"
MEMBER_FILE = "api/handlers.py"
MEMBER_SOURCE = "def list_entries():\n    return []\n"


@dataclass(frozen=True, slots=True)
class Workspace:
    """A two-repo workspace: the docs home that holds the books, and a product member that holds the source."""

    docs: Path
    member: Path


def head_of(repo: Path) -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def status_of(repo: Path) -> str:
    return subprocess.run(["git", "status", "--porcelain"], cwd=repo, check=True, capture_output=True, text=True).stdout
