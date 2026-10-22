from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from _fakes import StubRunner
from _milestones import write_milestone
from _pm import answer, verdict
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow import Registry
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv
from workhorse_workflows import author
from workhorse_workflows.author.pm.nodes import blueprint as pm_blueprint
from workhorse_workflows.author.shared.nodes import blueprint
from workhorse_workflows.author.shared.schemas import Defects
from workhorse_workflows.author.story_split import StorySplitDone, StorySplitFlow
from workhorse_workflows.author.story_split.nodes import blueprint as story_split_blueprint
from workhorse_workflows.author.story_split.schemas import StoryServices

EPIC = "accounts"
EPIC_DIR = "docs/epics/accounts"


class _Agent:
    def __init__(
        self,
        reviews: list[dict[str, str]] | None = None,
        writer: list[dict[str, str]] | None = None,
    ) -> None:
        self.reviews = list(reviews or [{}])
        self.writer = list(writer or [])
        self.calls: list[str] = []
        self.args: dict[str, list[dict[str, Any]]] = {}

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        stem = Path(node.prompt).stem
        self.calls.append(stem)
        self.args.setdefault(stem, []).append(ctx.as_dict())
        if stem == "split-stories":
            reply = self.writer.pop(0) if self.writer else {"status": "complete"}
            return "split", reply
        if stem == "review-inline":
            return "reviewed", verdict("story-split", self.reviews.pop(0))
        if stem == "answer":
            return "answered", answer("cover the reset flow")
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
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def derive(*args: Any, **kwargs: Any) -> StoryServices:
        return StoryServices()

    nodes = (
        Registry("story-split-test")
        .add_blueprints(blueprint, story_split_blueprint, pm_blueprint)
        .override(
            validate_coverage=validate,
            derive_story_services=derive,
        )
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
    assert agent.calls == ["split-stories", "review-inline"]
    assert agent.args["split-stories"][0]["epic"] == EPIC
    assert _git(repo, "branch", "--show-current") == branch_before
    assert _git(repo, "rev-parse", "--verify", "HEAD") == head_before


def test_mechanical_and_pm_findings_drive_a_bounded_resplit(
    repo: Path, tmp_path: Path
) -> None:
    agent = _Agent(reviews=[{"coverage": "reset flow is uncovered"}, {}])
    reports = [Defects(ok=False, errors="[orphan-seed] reset"), Defects(ok=True), Defects(ok=True)]

    result = drive(
        StorySplitFlow(epic=EPIC, repo_dir=str(repo)),
        _env(tmp_path, agent, reports),
    )

    assert isinstance(result, StorySplitDone)
    assert result.status == "accepted"
    assert result.reworks == 2
    notes = [row["rework_notes"] for row in agent.args["split-stories"]]
    assert notes[0] == ""
    assert notes[1] == "[orphan-seed] reset"
    assert "reset flow is uncovered" in notes[2]


def test_a_blocked_writer_is_answered_by_the_pm_then_retries(
    repo: Path, tmp_path: Path
) -> None:
    write_milestone(repo)
    agent = _Agent(writer=[{"status": "blocked", "notes": "which seed first?"}])

    result = drive(
        StorySplitFlow(epic=EPIC, repo_dir=str(repo)),
        _env(tmp_path, agent),
    )

    assert isinstance(result, StorySplitDone)
    assert result.status == "accepted"
    assert result.answers == 1
    assert agent.calls == ["split-stories", "answer", "split-stories", "review-inline"]
    assert "cover the reset flow" in agent.args["split-stories"][1]["note"]


def test_the_split_blocks_when_the_pm_never_passes(repo: Path, tmp_path: Path) -> None:
    agent = _Agent(reviews=[{"order": "wrong"}] * 4)

    result = drive(
        StorySplitFlow(epic=EPIC, repo_dir=str(repo)),
        _env(tmp_path, agent),
    )

    assert isinstance(result, StorySplitDone)
    assert result.status == "blocked"
    assert result.reworks == 3
