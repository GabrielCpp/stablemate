"""The scripted agent and the helpers the `fix` flow's end-to-end tests share."""
from __future__ import annotations

import json
import subprocess
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ostler import Ostler
from ostler.register import Record
from workhorse.pyflow.engine import RunEnv

from workhorse_workflows.coder.shared import commits
from workhorse_workflows.kit.git import commit_paths

RECORD = "widget-pagination"
TEXT = "the widget list does not paginate"
SLUG = "the-widget-list-does-not-paginate"
STORY_REL = f"0001-fixes/stories/{SLUG}"

RED_MAKEFILE = "lint:\n\t@echo 'pagination.go:1: undefined: pageSize'; exit 1\n"

SCREENSHOT = "__screenshots__/pagination.test.ts/paginates-1.png"


class ScriptedAgent:
    """The owner prompt, the resolver and the `docs` sub-flow's prompts, scripted on their arms."""

    def __init__(
        self,
        workspace: dict[str, Path],
        *,
        impl_blocked: int = 0,
        gate_red: int = 0,
        docs_blocks: int = 0,
        screenshots: int = 0,
        change: bool = True,
        explode: set[str] | None = None,
    ) -> None:
        self.workspace = workspace
        self.impl_blocked = impl_blocked
        self.gate_red = gate_red
        self.docs_blocks = docs_blocks
        self.screenshots = screenshots
        self.change = change
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
        """Write the change and commit what this turn wrote, so the gates and the commit have something to find."""
        if nth <= self.impl_blocked:
            return {
                "status": "blocked",
                "notes": "the page size is a product decision nobody has made",
            }
        if not self.change:
            return {"status": "done", "notes": "found nothing to change"}
        repo = self.workspace["api"]
        before = dirty_paths(repo)
        screenshot = repo / SCREENSHOT
        if screenshot.exists():
            screenshot.unlink()
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
        commit_paths(repo, message, *sorted(dirty_paths(repo) - before))
        if nth <= self.screenshots:
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            screenshot.write_bytes(b"\x89PNG failure")
        return {"status": "done", "notes": f"paginated the widget list on pass {nth}"}

    def _document_story(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if nth <= self.docs_blocks:
            return {"status": "blocked", "notes": "this change cannot be described as built"}
        docs_dir = Path.cwd() / "docs"
        feature = docs_dir / "services/api/concepts/widget.md"
        feature.parent.mkdir(parents=True, exist_ok=True)
        feature.write_text(
            "---\ntype: concept\nslug: widget\ntitle: Widget\n---\n"
            "# Widget\n\n- code: `repo://api/pagination.go`\n",
            encoding="utf-8",
        )
        return {
            "status": "documented",
            "nodes": ["docs/services/api/concepts/widget.md"],
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


def dirty_paths(repo: Path) -> set[str]:
    """Every path git reports as changed or untracked in *repo*."""
    status = subprocess.run(
        ["git", "status", "--porcelain", "-uall"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return {line[3:] for line in status.splitlines() if line}


def record_of(docs: Path, record_id: str = RECORD) -> Record:
    """The register's copy of a record, read fresh."""
    [found] = [r for r in Ostler(docs).records().records if r.id == record_id]
    return found


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
