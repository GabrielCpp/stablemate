from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

from _fakes import StubRunner
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow import Registry
from workhorse.pyflow import driver as pyflow_driver
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv
from workhorse_workflows import author
from workhorse_workflows.author.main.nodes import blueprint
from workhorse_workflows.author.shared.schemas import Defects
from workhorse_workflows.author.story_split import StorySplitDone, StorySplitFlow
from workhorse_workflows.author.story_split.nodes import blueprint as story_split_blueprint
from workhorse_workflows.author.story_split.schemas import StorySplitReceipt

EPIC = "accounts"
EPIC_DIR = "docs/epics/accounts"


class _Agent:
    def __init__(self, coverage: list[str] | None = None) -> None:
        self.coverage = list(coverage or ["ok"])
        self.calls: list[str] = []
        self.args: dict[str, list[dict[str, Any]]] = {}

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        stem = Path(node.prompt).stem
        self.calls.append(stem)
        self.args.setdefault(stem, []).append(ctx.as_dict())
        if stem == "split-stories":
            return "split", {"status": "complete"}
        if stem == "review-coverage":
            status = self.coverage.pop(0)
            return "reviewed", {"status": status, "notes": "cover the reset flow"}
        if stem == "resolve-operator":
            return "resolved", {"decision": "answered"}
        raise AssertionError(f"unexpected agent turn: {stem}")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    ).stdout.strip()


def _env(tmp_path: Path, agent: _Agent, reports: list[Defects] | None = None) -> RunEnv:
    queue = list(reports or [Defects(ok=True)])

    def validate(*args: Any, **kwargs: Any) -> Defects:
        return queue.pop(0)

    def record(_logger: Any, epic: str, *, repo_dir: str = "") -> StorySplitReceipt:
        path = Path(repo_dir) / EPIC_DIR / "story-split-receipt.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"status":"passed","graphDigest":"test"}\n', encoding="utf-8")
        return StorySplitReceipt(graph_digest="test", path=path.relative_to(repo_dir).as_posix())

    nodes = (
        Registry("story-split-test")
        .add_blueprints(blueprint, story_split_blueprint)
        .override(validate_coverage=validate, record_story_split_review=record)
    )
    writer = ArtifactWriter("story-split", tmp_path / "runs", run_id="t")
    return RunEnv(
        writer=writer,
        nodes=nodes,
        workflow_dir=Path(author.__file__).parent,
        session_id_path=writer.run_dir / ".session_id",
        config=RunConfig(),
        agent_runner=StubRunner(agent),
    )


def test_accepts_one_epic_graph_without_selecting_authoring_or_git(
    repo: Path, tmp_path: Path
) -> None:
    agent = _Agent()
    branch_before = _git(repo, "branch", "--show-current")
    head_before = _git(repo, "rev-parse", "--verify", "HEAD")

    result = drive(
        StorySplitFlow(epic=EPIC, repo_dir=str(repo)),
        _env(tmp_path, agent),
    )

    assert isinstance(result, StorySplitDone)
    assert result.status == "accepted"
    assert result.epic == EPIC
    assert result.epic_dir == EPIC_DIR
    assert result.receipt_path == f"{EPIC_DIR}/story-split-receipt.json"
    assert (repo / result.receipt_path).is_file()
    assert agent.calls == ["split-stories", "review-coverage"]
    assert agent.args["split-stories"][0]["epic"] == EPIC
    assert _git(repo, "branch", "--show-current") == branch_before
    assert _git(repo, "rev-parse", "--verify", "HEAD") == head_before


def test_coverage_findings_drive_a_bounded_resplit_worklist(
    repo: Path, tmp_path: Path
) -> None:
    agent = _Agent(coverage=["gaps", "ok"])
    reports = [Defects(ok=False, errors="[orphan-seed] reset"), Defects(ok=True), Defects(ok=True)]

    result = drive(
        StorySplitFlow(epic=EPIC, repo_dir=str(repo)),
        _env(tmp_path, agent, reports),
    )

    assert isinstance(result, StorySplitDone)
    assert result.coverage_reworks == 2
    split_args = agent.args["split-stories"]
    assert [row["rework_notes"] for row in split_args] == [
        "",
        "[orphan-seed] reset",
        "cover the reset flow",
    ]


def test_blocked_coverage_resolves_then_rechecks_the_same_epic(
    repo: Path, tmp_path: Path
) -> None:
    agent = _Agent(coverage=["blocked", "ok"])
    seen: list[Path] = []

    def answered(path: Path, **kwargs: Any) -> None:
        seen.append(path)

    env = _env(tmp_path, agent, [Defects(ok=True), Defects(ok=True)])
    with patch.object(pyflow_driver, "wait_for_answer", answered):
        result = drive(
            StorySplitFlow(epic=EPIC, repo_dir=str(repo)),
            replace(env, agent_runner=StubRunner(agent)),
        )

    assert isinstance(result, StorySplitDone)
    assert result.operator_resolutions == 1
    assert agent.calls == [
        "split-stories",
        "review-coverage",
        "resolve-operator",
        "split-stories",
        "review-coverage",
    ]
    assert agent.args["resolve-operator"][0]["block_stage"] == "coverage"
    assert seen == [repo / EPIC_DIR / "context.md"]
