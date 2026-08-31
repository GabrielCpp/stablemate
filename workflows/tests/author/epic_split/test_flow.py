from __future__ import annotations

import logging
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

from _fakes import StubRunner
from git import Repo
from ostler import Ostler
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow import driver as pyflow_driver
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv
from workhorse_workflows.author import epic_split as epic_split_package
from workhorse_workflows.author.epic_split.flow import EpicSplit
from workhorse_workflows.author.epic_split.nodes import prepare_epic_split, validate_epic_split
from workhorse_workflows.author.epic_split.schemas import EpicSplitValidation
from workhorse_workflows.author.workflow import workflow

ROADMAP = "docs/roadmaps/account-access.md"


def _planning_input(repo: Path) -> None:
    roadmap = repo / ROADMAP
    roadmap.parent.mkdir(parents=True)
    roadmap.write_text(
        "---\ntype: roadmap\ntitle: Account access\nstatus: approved\n---\n"
        "# Account access\n\n## User Journeys\n\nSign in, then recover access.\n",
        encoding="utf-8",
    )
    assert Ostler(repo).create_milestone(
        "account-access", "Account access", source_items=[ROADMAP]
    ).ok
    git = Repo(repo)
    git.index.add([ROADMAP, "docs/milestones/account-access.md", ".agents/ids.json"])
    git.index.commit("planning input")


def _set_epics(repo: Path, epics: list[str]) -> None:
    path = repo / "docs/milestones/account-access.md"
    text = path.read_text(encoding="utf-8")
    replacement = "epics:\n" + "".join(f"- {epic}\n" for epic in epics)
    path.write_text(text.replace("epics: []\n", replacement), encoding="utf-8")


class _Agent:
    def __init__(self, repo: Path, reviews: list[str]) -> None:
        self.repo = repo
        self.reviews = reviews
        self.calls: Counter[str] = Counter()

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        stem = Path(node.prompt).stem
        self.calls[stem] += 1
        if stem in {"split-epics", "rework-epic-split"}:
            okf = Ostler(self.repo)
            if not okf.list("epic"):
                assert okf.create_epic("sign-in", "Sign in").ok
                assert okf.create_epic("recover-access", "Recover access").ok
                _set_epics(self.repo, ["sign-in", "recover-access"])
            return "scripted", {"status": "complete", "notes": "split"}
        if stem == "review-epic-split":
            index = min(self.calls[stem], len(self.reviews)) - 1
            status = self.reviews[index]
            return "scripted", {"status": status, "notes": "repair order"}
        if stem == "resolve-epic-split":
            return "scripted", {
                "decision": "escalated",
                "notes": "owner must choose",
                "tried": ["read the roadmap"],
            }
        raise AssertionError(stem)


def _env(tmp_path: Path) -> RunEnv:
    writer = ArtifactWriter("author-epic-split", tmp_path / "runs", run_id="t")
    return RunEnv(
        writer=writer,
        workflow_dir=Path(epic_split_package.__file__).parent,
        session_id_path=writer.run_dir / ".session_id",
        config=RunConfig(),
        nodes=workflow.nodes,
    )


def test_creates_only_ordered_epic_skeletons_after_review_rework(
    repo: Path, tmp_path: Path
) -> None:
    _planning_input(repo)
    git = Repo(repo)
    before = git.head.commit.hexsha
    agent = _Agent(repo, ["needs_rework", "approved"])

    result = drive(
        EpicSplit(roadmap=ROADMAP, repo_dir=str(repo)),
        replace(_env(tmp_path), agent_runner=StubRunner(agent)),
    )

    assert isinstance(result, EpicSplitValidation)
    assert result.ok
    assert result.ordered_epics == ["sign-in", "recover-access"]
    assert agent.calls == {
        "split-epics": 1,
        "review-epic-split": 2,
        "rework-epic-split": 1,
    }
    assert Ostler(repo).list("seed") == []
    assert Ostler(repo).list("story") == []
    assert git.active_branch.name == "main"
    assert git.head.commit.hexsha == before


def test_block_is_diagnosed_then_retried_after_operator_resume(repo: Path, tmp_path: Path) -> None:
    _planning_input(repo)
    agent = _Agent(repo, ["blocked", "approved"])

    with patch.object(pyflow_driver, "wait_for_answer", return_value=None):
        result = drive(
            EpicSplit(roadmap=ROADMAP, repo_dir=str(repo)),
            replace(_env(tmp_path), agent_runner=StubRunner(agent)),
        )

    assert isinstance(result, EpicSplitValidation)
    assert result.ok
    assert agent.calls["resolve-epic-split"] == 1
    assert agent.calls["split-epics"] == 2


def test_validation_rejects_seed_and_prose_authored_during_split(repo: Path) -> None:
    _planning_input(repo)
    context = prepare_epic_split(logging.getLogger("test"), ROADMAP, repo_dir=str(repo))
    okf = Ostler(repo)
    assert okf.create_epic("sign-in", "Sign in").ok
    _set_epics(repo, ["sign-in"])
    epic_path = next((repo / "docs/epics").glob("*/epic.md"))
    epic_path.write_text(
        epic_path.read_text(encoding="utf-8").replace(
            "## Seeds", "## User Outcome\n\nPeople sign in.\n\n## Seeds"
        ),
        encoding="utf-8",
    )

    result = validate_epic_split(logging.getLogger("test"), context)

    assert not result.ok
    assert "authored prose" in result.errors
