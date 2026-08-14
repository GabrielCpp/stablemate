"""Shared builders and the scripted agent for the stage-plan suite.

The agent stands in for three different turns — the parent's slicing turn and, inside each
handed-off phase, that phase's decomposition and implementation. Keying the reply on the
node id alone is not enough for the second: every phase asks `decompose-implementation-plan`,
and the whole point of the flow is that each one is asked about a *different* document. So
the decomposition is looked up by the slice whose text the turn was handed.
"""
from __future__ import annotations

import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from workhorse_workflows.coder.stage_plan.inventory import (
    prepare_slices,
    snapshot_staged_plan,
)
from workhorse_workflows.coder.stage_plan.schemas import PlanSlicing, PreparedSlices

PLAN_TEXT = """# Build two ordered pieces

## Implementation phases

### Phase 1 — First piece

Create `src/first.txt`.

### Phase 2 — Second piece

Create `src/second.txt`, which imports the first.
"""

FIRST = "Phase 1 — First piece"
SECOND = "Phase 2 — Second piece"


def command(code: str) -> dict[str, Any]:
    return {"argv": [sys.executable, "-c", code], "cwd": ".", "timeout_s": 30}


def exists(*paths: str) -> dict[str, Any]:
    condition = " and ".join(f"Path({path!r}).is_file()" for path in paths)
    return command(f"from pathlib import Path; assert {condition}")


def slice_of(identity: str, heading: str, path: str) -> dict[str, Any]:
    return {
        "id": identity,
        "title": heading,
        "covers": [heading],
        "body": f"# {heading}\n\nCreate `{path}` and nothing else.\n",
    }


def slicing(
    *slices: dict[str, Any],
    headings: list[str] | None = None,
    status: str = "ready",
    final: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "summary": "one phase per heading",
        "phase_headings": headings if headings is not None else [FIRST, SECOND],
        "slices": list(slices),
        "final_verification": (
            [exists("src/first.txt", "src/second.txt")] if final is None else final
        ),
    }


def task(task_id: str, path: str) -> dict[str, Any]:
    return {
        "id": task_id,
        "title": task_id.replace("-", " ").title(),
        "objective": f"Implement {task_id}.",
        "acceptance": [f"{path} exists."],
        "depends_on": [],
        "paths": [path],
        "verification": [exists(path)],
        "commit_type": "feat",
        "commit_scope": "",
    }


def decomposition(task_id: str, path: str) -> dict[str, Any]:
    return {
        "status": "ready",
        "summary": f"one packet for {task_id}",
        "tasks": [task(task_id, path)],
        "final_verification": [exists(path)],
    }


@pytest.fixture
def origin(
    tmp_path: Path,
    repo: Path,
    git: Callable[..., subprocess.CompletedProcess],
) -> Path:
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "--bare", "-q", str(bare))
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-qu", "origin", "main")
    return bare


class Agent:
    """Answers the slicing turn, then each phase's decomposition and implementation."""

    def __init__(
        self,
        repo: Path,
        proposal: dict[str, Any],
        *,
        phases: dict[str, dict[str, Any]],
        edits: dict[str, dict[str, str]],
        skip_edit_for: str = "",
    ) -> None:
        self.repo = repo
        self.proposal = proposal
        self.phases = phases
        self.edits = edits
        self.skip_edit_for = skip_edit_for
        self.calls: list[str] = []

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        data = ctx.as_dict()
        self.calls.append(node.id)
        if node.id == "slice-implementation-plan":
            reply: Any = self.proposal
        elif node.id == "decompose-implementation-plan":
            reply = self.phases[self._heading(data["plan_text"])]
        elif node.id == "review-plan-implementation":
            reply = {"status": "approved", "summary": "phase reviewed"}
        elif node.id == "implement-plan-task-tests":
            task_id = data["task"]["id"]
            reply = {"status": "done", "notes": f"tests for {task_id}"}
        else:
            task_id = data["task"]["id"]
            if task_id != self.skip_edit_for:
                for relative, content in self.edits.get(task_id, {}).items():
                    target = self.repo / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(content, encoding="utf-8")
            reply = {"status": "done", "notes": f"handled {task_id}"}
        return f"(scripted) {node.prompt}", reply

    def _heading(self, plan_text: str) -> str:
        for heading in self.phases:
            if heading in plan_text:
                return heading
        raise AssertionError(f"no scripted phase matches {plan_text!r}")

    def count(self, node_id: str) -> int:
        return Counter(self.calls)[node_id]


def context_of(tmp_path: Path, repo: Path, logger: Any, plan_text: str = PLAN_TEXT):
    plan = tmp_path / "source-plan.md"
    plan.write_text(plan_text, encoding="utf-8")
    return snapshot_staged_plan(logger, str(plan), str(tmp_path / "run"), str(repo))


def prepared_of(context: Any, logger: Any, proposal: dict[str, Any]) -> PreparedSlices:
    return prepare_slices(logger, PlanSlicing.model_validate(proposal), context)
