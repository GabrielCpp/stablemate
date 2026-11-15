"""Git helpers and a scripted agent keyed by prompt."""
from __future__ import annotations

import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import override

import pytest

from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.context import WorkflowContext
from workhorse.pyflow.engine import RunEnv
from workhorse.runner.backends.null import NullBackend
from workhorse.runner.ladder import AgentRunner
from workhorse.runner.spec import AgentNode

from workhorse_workflows import okf_book
from workhorse_workflows.okf_book.workflow import workflow

FIX_COMMIT_NODE = "fix-refused-commit"

Reply = Callable[[dict[str, object]], dict[str, object]]

def run_env(runs_dir: Path, runner: AgentRunner) -> RunEnv:
    """An okf-book run under `runs_dir` whose agent turns go to `runner`."""
    writer = ArtifactWriter("okf-book", runs_dir, run_id="t0")
    return RunEnv(
        writer=writer,
        workflow_dir=Path(okf_book.__file__).parent,
        session_id_path=writer.run_dir / ".session_id",
        config=RunConfig(),
        nodes=workflow.nodes,
        agent_runner=runner,
    )


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


def install_book_skill(home: Path, monkeypatch: pytest.MonkeyPatch | None = None) -> None:
    """The `ostler-book` skill under `home`, which a prompt that references it needs to render. Given a monkeypatch, `home` becomes the home of the process."""
    skill = home / ".claude/skills/ostler-book/SKILL.md"
    skill.parent.mkdir(parents=True)
    _ = skill.write_text("---\nname: ostler-book\nmetadata:\n  name: ostler-book\n---\n", encoding="utf-8")
    if monkeypatch is not None:
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("AGENT_CLI", "claude")


def dry_run_said(tmp_path: Path, flow: str) -> subprocess.CompletedProcess[str]:
    """A `--dry-run` of the named flow from a one-commit repo under `tmp_path`."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "kept.txt").write_text("kept\n", encoding="utf-8")
    git(repo, "add", "kept.txt")
    git(repo, "commit", "-q", "-m", "chore: start")
    home = tmp_path / "home"
    install_book_skill(home)
    return subprocess.run(
        [sys.executable, "-c", "from workhorse_workflows.okf_book.workflow import main; main()", "run", flow, "--dry-run", "--runs-dir", str(tmp_path / "runs")],
        cwd=repo,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
