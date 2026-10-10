"""The scripted agent and the helpers the `fix` flow's end-to-end tests share."""
from __future__ import annotations

import json
import subprocess
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from workhorse.pyflow.engine import RunEnv

from workhorse_workflows.coder.shared import commits
from workhorse_workflows.kit.git import commit_all

BULLET = "widget-pagination"
TEXT = "the widget list does not paginate"
SLUG = "the-widget-list-does-not-paginate"
STORY_REL = f"docs/epics/0001-fixes/stories/{SLUG}"

BACKLOG = f"""# Backlog

## Filed by coder

- [{BULLET}] {TEXT}
"""

RED_MAKEFILE = "lint:\n\t@echo 'pagination.go:1: undefined: pageSize'; exit 1\n"


class ScriptedAgent:
    """The owner prompt, the resolver and the `docs` sub-flow's prompts, scripted on their arms."""

    def __init__(
        self,
        workspace: dict[str, Path],
        *,
        impl_blocked: int = 0,
        gate_red: int = 0,
        docs_blocks: int = 0,
        explode: set[str] | None = None,
    ) -> None:
        self.workspace = workspace
        self.impl_blocked = impl_blocked
        self.gate_red = gate_red
        self.docs_blocks = docs_blocks
        self.explode = explode or set()
        self.calls: list[str] = []
        self.args: list[dict[str, Any]] = []


    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        stem = Path(node.prompt).stem
        data = ctx.as_dict()
        self.calls.append(stem)
        self.args.append(data)
        if stem in self.explode:
            raise RuntimeError(f"killed during {stem}")
        handler = getattr(self, f"_{stem.replace('-', '_')}")
        return f"(scripted) {node.prompt}", handler(data, self.counts()[stem])

    def counts(self) -> Counter[str]:
        return Counter(self.calls)

    def args_for(self, stem: str) -> list[dict[str, Any]]:
        return [a for s, a in zip(self.calls, self.args, strict=True) if s == stem]


    def _fix_item(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """Write the change, so the gates and the commit have something to find."""
        if nth <= self.impl_blocked:
            return {
                "status": "blocked",
                "notes": "the page size is a product decision nobody has made",
            }
        repo = self.workspace["api"]
        (repo / "pagination.go").write_text(f"// pass {nth}\n", encoding="utf-8")
        makefile = repo / "Makefile"
        if nth <= self.gate_red:
            makefile.write_text(RED_MAKEFILE, encoding="utf-8")
        elif makefile.exists():
            makefile.unlink()
        message = commits.message(
            "fix",
            commits.scope(repo.name),
            TEXT,
            epic=str(data["epic"]),
            story=str(data["story_id"]),
        )
        commit_all(repo, message)
        return {"status": "done", "notes": f"paginated the widget list on pass {nth}"}

    def _document_story(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if nth <= self.docs_blocks:
            return {"status": "blocked", "notes": "this change cannot be described as built"}
        story_path = Path(str(data["story_path"]))
        docs_dir = next(parent for parent in story_path.parents if parent.name == "docs")
        feature = docs_dir / "features/api/concepts/widget.md"
        feature.parent.mkdir(parents=True, exist_ok=True)
        feature.write_text(
            "---\ntype: concept\nslug: widget\ntitle: Widget\n---\n"
            "# Widget\n\n- code: `repo://api/pagination.go`\n",
            encoding="utf-8",
        )
        return {
            "status": "documented",
            "nodes": ["docs/features/api/concepts/widget.md"],
            "notes": f"documented on pass {nth}",
        }

    def _resolve_operator(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """The resolver's say on a block, which this fake declines to give."""
        return {"decision": "escalated", "summary": "no answer to give"}


def answers(seen: list[str]) -> Callable[..., None]:
    """A stand-in for the human the `Await` is waiting on."""

    def answered(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text(encoding="utf-8"))
        path.write_text(
            "STATUS: ANSWERED\n\nTwenty per page, as the widget grid already does.\n",
            encoding="utf-8",
        )

    return answered


def backlog(docs: Path) -> str:
    return (docs / "docs" / "backlog.md").read_text(encoding="utf-8")


def output(run_env: RunEnv, node: Any) -> dict[str, Any]:
    """A node's recorded output — the artifact, not the return value the flow saw."""
    path = run_env.writer.run_dir / node.__name__ / "output.json"
    return json.loads(path.read_text(encoding="utf-8"))


def log_of(repo: Path) -> list[str]:
    return subprocess.run(
        ["git", "log", "--format=%s"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.split("\n")


def assert_agent_story_commit(repo: Path, agent: ScriptedAgent) -> None:
    story_id = str(agent.args_for("fix-item")[0]["story_id"])
    subject = log_of(repo)[0]
    assert subject.startswith("fix(api): ")
    assert story_id not in subject


def branch_of(repo: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
