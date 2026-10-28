from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any

from _fakes import StubRunner
from _pm import answer, verdict
from _milestones import write_milestone
from git import Repo
from ostler import Ostler
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv
from workhorse_workflows.author import epic_split as epic_split_package
from workhorse_workflows.author.epic_split.flow import EpicSplit
from workhorse_workflows.author.epic_split.nodes import prepare_epic_split, validate_epic_split
from workhorse_workflows.author.epic_split.schemas import EpicSplitDone
from workhorse_workflows.author.workflow import workflow
from _epics import epics_root

MILESTONE = "docs/milestones/account-access/milestone.md"


def _planning_input(repo: Path) -> None:
    path = write_milestone(repo)
    git = Repo(repo)
    git.index.add([path])
    git.index.commit("planning input")


def _set_epics(repo: Path, epics: list[str]) -> None:
    path = repo / MILESTONE
    text = path.read_text(encoding="utf-8")
    replacement = "epics:\n" + "".join(f"- {epic}\n" for epic in epics)
    path.write_text(text.replace("epics: []\n", replacement), encoding="utf-8")


class _Agent:
    def __init__(self, repo: Path, reviews: list[dict[str, str]], blocks: int = 0) -> None:
        self.repo = repo
        self.reviews = reviews
        self.blocks = blocks
        self.calls: Counter[str] = Counter()
        self.notes: list[str] = []
        self.review_notes: list[str] = []

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        stem = Path(node.prompt).stem
        self.calls[stem] += 1
        if stem in {"split-epics", "rework-epic-split"}:
            data = ctx.as_dict()
            self.notes.append(str(data.get("note", "")))
            self.review_notes.append(str(data.get("review_notes", "")))
            if self.blocks:
                self.blocks -= 1
                return "scripted", {"status": "blocked", "notes": "which order?"}
            okf = Ostler(self.repo)
            if not okf.list("epic"):
                assert okf.create_epic("sign-in", "Sign in").ok
                assert okf.create_epic("recover-access", "Recover access").ok
                _set_epics(self.repo, ["sign-in", "recover-access"])
            return "scripted", {"status": "complete", "notes": "split"}
        if stem == "review-inline":
            index = min(self.calls[stem], len(self.reviews)) - 1
            return "scripted", verdict("epic-split", self.reviews[index])
        if stem == "answer":
            return "scripted", answer("sign-in first")
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
    agent = _Agent(repo, [{"order": "sign-in must come first"}, {}])

    result = drive(
        EpicSplit(repo_dir=str(repo)),
        replace(_env(tmp_path), agent_runner=StubRunner(agent)),
    )

    assert isinstance(result, EpicSplitDone)
    assert result.status == "accepted"
    assert result.ordered_epics == ["sign-in", "recover-access"]
    assert result.reworks == 1
    assert agent.calls == {
        "split-epics": 1,
        "review-inline": 2,
        "rework-epic-split": 1,
    }
    assert Ostler(repo).list("seed") == []
    assert Ostler(repo).list("story") == []
    assert git.active_branch.name == "main"
    assert git.head.commit.hexsha == before


def test_a_passing_review_writes_the_receipt_beside_the_milestone(
    repo: Path, tmp_path: Path
) -> None:
    _planning_input(repo)

    drive(
        EpicSplit(repo_dir=str(repo)),
        replace(_env(tmp_path), agent_runner=StubRunner(_Agent(repo, [{}]))),
    )

    receipt = repo / "docs/milestones/account-access/artifacts/pm-receipt.json"
    assert json.loads(receipt.read_text(encoding="utf-8"))["stage"] == "epic-split"


def test_the_review_findings_reach_the_rework_turn(repo: Path, tmp_path: Path) -> None:
    _planning_input(repo)
    agent = _Agent(repo, [{"order": "sign-in must come first"}, {}])

    drive(
        EpicSplit(repo_dir=str(repo)),
        replace(_env(tmp_path), agent_runner=StubRunner(agent)),
    )

    assert agent.review_notes[0] == ""
    assert "[order] the subject: sign-in must come first" in agent.review_notes[1]


def test_a_blocked_writer_is_answered_by_the_pm_and_retried(repo: Path, tmp_path: Path) -> None:
    _planning_input(repo)
    agent = _Agent(repo, [{}], blocks=1)

    result = drive(
        EpicSplit(repo_dir=str(repo)),
        replace(_env(tmp_path), agent_runner=StubRunner(agent)),
    )

    assert isinstance(result, EpicSplitDone)
    assert result.status == "accepted"
    assert result.answers == 1
    assert agent.calls["answer"] == 1
    assert agent.calls["split-epics"] == 2
    assert "sign-in first" in agent.notes[1]
    ledger = repo / "docs/milestones/account-access/grills/pm.md"
    assert "sign-in first" in ledger.read_text(encoding="utf-8")


def test_a_writer_that_keeps_asking_ends_blocked_after_two_answers(
    repo: Path, tmp_path: Path
) -> None:
    _planning_input(repo)
    agent = _Agent(repo, [{}], blocks=5)

    result = drive(
        EpicSplit(repo_dir=str(repo)),
        replace(_env(tmp_path), agent_runner=StubRunner(agent)),
    )

    assert isinstance(result, EpicSplitDone)
    assert result.status == "blocked"
    assert result.notes == "which order?"
    assert agent.calls["answer"] == 2


def test_a_review_that_never_passes_ends_blocked_with_its_findings(
    repo: Path, tmp_path: Path
) -> None:
    _planning_input(repo)
    agent = _Agent(repo, [{"order": "still wrong"}])

    result = drive(
        EpicSplit(repo_dir=str(repo)),
        replace(_env(tmp_path), agent_runner=StubRunner(agent)),
    )

    assert isinstance(result, EpicSplitDone)
    assert result.status == "blocked"
    assert "still wrong" in result.notes
    assert agent.calls["review-inline"] == 4
    assert agent.calls["rework-epic-split"] == 3
    receipt = repo / "docs/milestones/account-access/artifacts/pm-receipt.json"
    assert not receipt.exists()


def test_validation_rejects_seed_and_prose_authored_during_split(repo: Path) -> None:
    _planning_input(repo)
    context = prepare_epic_split(logging.getLogger("test"), repo_dir=str(repo))
    okf = Ostler(repo)
    assert okf.create_epic("sign-in", "Sign in").ok
    _set_epics(repo, ["sign-in"])
    epic_path = next((epics_root()).glob("*/epic.md"))
    epic_path.write_text(
        epic_path.read_text(encoding="utf-8").replace(
            "## Seeds", "## User Outcome\n\nPeople sign in.\n\n## Seeds"
        ),
        encoding="utf-8",
    )

    result = validate_epic_split(logging.getLogger("test"), context)

    assert not result.ok
    assert "authored prose" in result.errors
