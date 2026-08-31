from __future__ import annotations

import logging
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any

from _fakes import StubRunner
from git import Repo
from ostler import Ostler
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv
from workhorse_workflows.author import milestone as milestone_package
from workhorse_workflows.author.milestone.flow import Milestone
from workhorse_workflows.author.milestone.nodes import prepare_milestone, validate_milestone
from workhorse_workflows.author.milestone.schemas import MilestoneValidation
from workhorse_workflows.author.workflow import workflow

ROADMAP = "docs/roadmaps/account-access.md"


def _roadmap(repo: Path) -> None:
    path = repo / ROADMAP
    path.parent.mkdir(parents=True)
    path.write_text(
        "---\ntype: roadmap\ntitle: Account access\nstatus: approved\n---\n"
        "# Account access\n\n## Outcome\n\nPeople can access their account.\n",
        encoding="utf-8",
    )


class _Agent:
    def __init__(self, repo: Path) -> None:
        self.repo = repo
        self.calls: Counter[str] = Counter()

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        stem = Path(node.prompt).stem
        self.calls[stem] += 1
        if stem != "build-milestone":
            raise AssertionError(stem)
        okf = Ostler(self.repo)
        if not okf.list("milestone"):
            result = okf.create_milestone(
                "account-access", "Account access", source_items=[ROADMAP]
            )
            assert result.ok, result.message
        return "scripted", {"status": "complete", "notes": "one milestone"}


def _env(tmp_path: Path) -> RunEnv:
    writer = ArtifactWriter("author-milestone", tmp_path / "runs", run_id="t")
    return RunEnv(
        writer=writer,
        workflow_dir=Path(milestone_package.__file__).parent,
        session_id_path=writer.run_dir / ".session_id",
        config=RunConfig(),
        nodes=workflow.nodes,
    )


def test_builds_then_reuses_one_milestone_without_epics(repo: Path, tmp_path: Path) -> None:
    _roadmap(repo)
    git = Repo(repo)
    git.index.add([ROADMAP])
    git.index.commit("roadmap")
    before = git.head.commit.hexsha

    first_agent = _Agent(repo)
    first = drive(
        Milestone(roadmap=ROADMAP, repo_dir=str(repo)),
        replace(_env(tmp_path), agent_runner=StubRunner(first_agent)),
    )

    assert isinstance(first, MilestoneValidation)
    assert first.ok and not first.reused
    assert len(Ostler(repo).list("milestone")) == 1
    assert Ostler(repo).list("epic") == []
    assert git.active_branch.name == "main"
    assert git.head.commit.hexsha == before

    second_agent = _Agent(repo)
    second = drive(
        Milestone(roadmap=ROADMAP, repo_dir=str(repo)),
        replace(_env(tmp_path / "again"), agent_runner=StubRunner(second_agent)),
    )

    assert isinstance(second, MilestoneValidation)
    assert second.ok and second.reused
    assert len(Ostler(repo).list("milestone")) == 1
    assert second_agent.calls == {"build-milestone": 1}


def test_validation_rejects_an_epic_created_by_the_milestone_stage(repo: Path) -> None:
    _roadmap(repo)
    context = prepare_milestone(logging.getLogger("test"), ROADMAP, repo_dir=str(repo))
    okf = Ostler(repo)
    assert okf.create_milestone("account-access", "Account access", source_items=[ROADMAP]).ok
    assert okf.create_epic("sign-in", "Sign in").ok

    result = validate_milestone(logging.getLogger("test"), context)

    assert not result.ok
    assert "must not create or edit epic documents" in result.errors
