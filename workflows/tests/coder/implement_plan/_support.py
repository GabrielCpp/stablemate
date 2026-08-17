"""Shared builders and scripted agent for implement-plan tests."""
from __future__ import annotations

import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from workhorse_workflows.coder.implement_plan.inventory import prepare_plan, snapshot_plan
from workhorse_workflows.coder.implement_plan.schemas import PlanDecomposition, PreparedPlan


def _command(code: str) -> dict[str, Any]:
    return {"argv": [sys.executable, "-c", code], "cwd": ".", "timeout_s": 30}


def _task(
    task_id: str,
    path: str,
    *,
    depends_on: list[str] | None = None,
    verification: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": task_id,
        "title": f"Implement {task_id.replace('-', ' ')}",
        "objective": f"Implement {task_id}.",
        "acceptance": [f"{path} contains {task_id}."],
        "depends_on": depends_on or [],
        "paths": [path],
        "verification": verification
        or [_command(f"from pathlib import Path; assert Path({path!r}).is_file()")],
        "commit_type": "feat",
        "commit_scope": "",
    }


def _decomposition(
    *tasks: dict[str, Any], final: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    paths = [task["paths"][0] for task in tasks]
    condition = " and ".join(f"Path({path!r}).is_file()" for path in paths)
    return {
        "status": "ready",
        "summary": "ordered packets",
        "tasks": list(tasks),
        "final_verification": final
        or [_command(f"from pathlib import Path; assert {condition}")],
    }


def _issue(issue_id: str, path: str, *, finding: str = "Observed blocking defect.") -> dict[str, Any]:
    return _task(issue_id, path) | {
        "finding": finding,
        "commit_type": "fix",
    }


def _review(*issues: dict[str, Any], summary: str = "independent review") -> dict[str, Any]:
    return {
        "status": "issues" if issues else "approved",
        "summary": summary,
        "issues": list(issues),
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


class _Agent:
    def __init__(
        self,
        repo: Path,
        decomposition: dict[str, Any],
        *,
        reworked: list[dict[str, Any]] | None = None,
        edits: dict[str, dict[str, str]] | None = None,
        repair_edits: dict[str, dict[str, str]] | None = None,
        repair_steps: dict[str, list[dict[str, str]]] | None = None,
        repair_removes: list[str] | None = None,
        planning_edits: dict[str, str] | None = None,
        test_edits: dict[str, dict[str, str]] | None = None,
        commit_on_task: str = "",
        blocked_on_task: str = "",
        reviews: list[dict[str, Any]] | None = None,
    ) -> None:
        self.repo = repo
        # Each planning turn consumes the next proposal, so a rejected decomposition can
        # be followed by its correction; the last one repeats for every further turn.
        self.decompositions = [decomposition, *(reworked or [])]
        self.decomposition_index = 0
        self.edits = edits or {}
        self.repair_edits = repair_edits or {}
        # A repair turn that writes something *different* on each pass, indexed by the
        # `repair` counter the flow puts in the prompt. `repair_edits` cannot express
        # that — it replays one set of writes forever — so a fixture where the gate
        # reports a fresh defect after each repair needs this instead.
        self.repair_steps = repair_steps or {}
        # Absolute paths a repair turn deletes. A committed-tree failure is retracted and
        # handed back for repair, so a fixture that fails only after a commit needs the
        # repair turn to undo the thing the commit created — otherwise the next worktree
        # verification fails for a reason the packet never had.
        self.repair_removes = [Path(path) for path in repair_removes or []]
        self.planning_edits = planning_edits or {}
        self.test_edits = test_edits or {}
        self.commit_on_task = commit_on_task
        self.blocked_on_task = blocked_on_task
        self.reviews = reviews or [_review()]
        self.review_index = 0
        self.calls: list[str] = []
        self.turn_args: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        data = ctx.as_dict()
        self.calls.append(node.id)
        self.turn_args.append((node.id, data))
        if node.id == "decompose-implementation-plan":
            self._write(self.planning_edits)
            index = min(self.decomposition_index, len(self.decompositions) - 1)
            self.decomposition_index += 1
            reply = self.decompositions[index]
        elif node.id == "review-plan-implementation":
            reply = self.reviews[min(self.review_index, len(self.reviews) - 1)]
            self.review_index += 1
        elif node.id == "implement-plan-task-tests":
            task_id = data["task"]["id"]
            self._write(self.test_edits.get(task_id, {}))
            reply = {
                "status": "blocked" if task_id == self.blocked_on_task else "done",
                "notes": f"tests for {task_id}",
            }
        else:
            task_id = (data.get("task") or data["issue"])["id"]
            repairing = node.id in {"repair-plan-task", "repair-plan-review-issue"}
            if repairing:
                for target in self.repair_removes:
                    target.unlink(missing_ok=True)
            if repairing and task_id in self.repair_steps:
                steps = self.repair_steps[task_id]
                writes = steps[min(int(data.get("repair", 1)) - 1, len(steps) - 1)]
            elif repairing:
                writes = self.repair_edits.get(task_id, {})
            else:
                writes = self.edits.get(task_id, {})
            self._write(writes)
            if task_id == self.commit_on_task:
                subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True)
                subprocess.run(
                    ["git", "commit", "-qm", "feat(workflows): agent bypass"],
                    cwd=self.repo,
                    check=True,
                )
            reply = {
                "status": "blocked" if task_id == self.blocked_on_task else "done",
                "notes": f"handled {task_id}",
            }
        return f"(scripted) {node.prompt}", reply

    def _write(self, values: dict[str, str]) -> None:
        for relative, content in values.items():
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

    def count(self, node_id: str) -> int:
        return Counter(self.calls)[node_id]

    def args_for(self, node_id: str) -> list[dict[str, Any]]:
        return [data for called, data in self.turn_args if called == node_id]


def _context(
    tmp_path: Path,
    repo: Path,
    logger: Any,
    plan_text: str = "# Plan\n",
    plan: Path | None = None,
):
    remotes = subprocess.run(
        ["git", "remote"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.split()
    if "origin" not in remotes:
        bare = tmp_path / "direct-origin.git"
        subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
        subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=repo, check=True)
        subprocess.run(["git", "push", "-qu", "origin", "main"], cwd=repo, check=True)
    plan = plan or tmp_path / "plan.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text(plan_text, encoding="utf-8")
    return snapshot_plan(logger, str(plan), str(tmp_path / "run"), str(repo))


def _prepared(context: Any, logger: Any, *tasks: dict[str, Any]) -> PreparedPlan:
    proposal = PlanDecomposition.model_validate(_decomposition(*tasks))
    return prepare_plan(logger, proposal, context)
