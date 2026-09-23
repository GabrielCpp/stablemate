"""Paddock fixture apps, git helpers, and a scripted agent for the listing turn."""
from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import override

from workhorse.context import WorkflowContext
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv
from workhorse.runner.backends.null import NullBackend
from workhorse.runner.ladder import AgentRunner
from workhorse.runner.spec import AgentNode

from workhorse_workflows.okf_book.surface import EntryPoint, EntryPointListing
from workhorse_workflows.okf_book.workflow import OkfBook

driver: Callable[[OkfBook, RunEnv], object] = drive

APPS = Path(__file__).resolve().parents[3] / "paddock" / "data" / "apps"


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return done.stdout


def commits(repo: Path) -> list[str]:
    """Every commit subject, newest first."""
    return git(repo, "log", "--format=%s").splitlines()


def listing(*slugs: str) -> EntryPointListing:
    return EntryPointListing(entry_points=tuple(EntryPoint(slug=s, title=s.title()) for s in slugs))


class ListingRunner(AgentRunner):
    """Answers every agent turn with one entry-point listing, and counts the turns."""

    def __init__(self, reply: EntryPointListing) -> None:
        super().__init__(backend=NullBackend())
        self.reply: EntryPointListing = reply
        self.turns: int = 0

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
        validate: Callable[[dict[str, object]], object] | None = None,
    ) -> tuple[str, dict[str, object]]:
        self.turns += 1
        reply: dict[str, object] = {"entry_points": [p.model_dump() for p in self.reply.entry_points]}
        if validate is not None:
            _ = validate(reply)
        return "scripted", reply
