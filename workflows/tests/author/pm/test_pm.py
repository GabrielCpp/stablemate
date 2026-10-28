from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from _fakes import StubRunner
from _milestones import write_milestone
from _pm import amendment, answer, verdict
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow import WorkflowFailed
from workhorse.runner.backends.null import NullBackend
from workhorse.pyflow import park as pyflow_park
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv
from workhorse_workflows import author
from workhorse_workflows.author.pm import GapAnswer, PMReview
from workhorse_workflows.author.pm.angles import ANGLES, stage_prompt
from workhorse_workflows.author.pm.answer import accepts, note_for
from workhorse_workflows.author.pm.flow import complete
from workhorse_workflows.author.pm.receipt import (
    RECEIPT_NAME,
    pm_receipt_current,
    write_pm_receipt,
)
from workhorse_workflows.author.pm.schemas import Answer, GapAnswered, PMResult, Verdict
from workhorse_workflows.author.workflow import workflow
from _epics import epics_root

PM = Path(author.__file__).parent


def _story(repo: Path) -> str:
    write_milestone(repo)
    path = epics_root() / "0001-accounts/stories/01-sign-in/story.md"
    path.parent.mkdir(parents=True)
    path.write_text("# Story: Sign in\n", encoding="utf-8")
    return str(path)


class _Agent:
    def __init__(self, replies: list[dict[str, Any]]) -> None:
        self.replies = list(replies)
        self.calls: Counter[str] = Counter()
        self.args: list[dict[str, Any]] = []

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        stem = Path(node.prompt).stem
        self.calls[stem] += 1
        self.args.append(ctx.as_dict())
        return "scripted", self.replies.pop(0)


class _Delegating(NullBackend):
    supports_subagents = True


def _env(tmp_path: Path, agent: _Agent, *, subagents: bool = False) -> RunEnv:
    runner = StubRunner(agent, _Delegating() if subagents else None)
    writer = ArtifactWriter("author-pm", tmp_path / "runs", run_id="t")
    return RunEnv(
        writer=writer,
        workflow_dir=PM,
        session_id_path=writer.run_dir / ".session_id",
        config=RunConfig(),
        nodes=workflow.nodes,
        agent_runner=runner,
    )


@pytest.mark.parametrize("stage", sorted(ANGLES))
def test_every_angle_has_a_prompt_and_the_stage_a_brief(stage: str) -> None:
    names = [angle.name for angle in ANGLES[stage]]
    assert len(names) == len(set(names))
    for angle in ANGLES[stage]:
        assert (PM / angle.prompt).read_text(encoding="utf-8").strip()
    assert (PM / stage_prompt(stage)).read_text(encoding="utf-8").strip()


def test_a_review_must_judge_every_angle_exactly_once() -> None:
    check = complete(ANGLES["story"])
    good = Verdict.model_validate(verdict("story"))
    check(good)

    missing = Verdict(angles=good.angles[1:])
    with pytest.raises(ValueError, match="journey"):
        check(missing)

    extra = Verdict(angles=[*good.angles, good.angles[0]])
    with pytest.raises(ValueError):
        check(extra)


def test_a_passing_review_writes_a_receipt_and_a_failing_one_does_not(
    repo: Path, tmp_path: Path
) -> None:
    story = _story(repo)
    failing = _Agent([verdict("story", {"journey": "no outcome"})])

    result = drive(
        PMReview(stage="story", subject=story, epic="accounts", repo_dir=str(repo)),
        _env(tmp_path, failing),
    )

    assert isinstance(result, PMResult)
    assert not result.passed
    assert result.receipt_path == ""
    assert "[journey] the subject: no outcome. Repair: repair it" in result.notes
    assert not (repo / story).with_name(RECEIPT_NAME).exists()

    passing = _Agent([verdict("story")])
    result = drive(
        PMReview(stage="story", subject=story, epic="accounts", repo_dir=str(repo)),
        _env(tmp_path / "second", passing),
    )

    assert isinstance(result, PMResult)
    assert result.passed
    assert (repo / story).with_name(RECEIPT_NAME).is_file()


@pytest.mark.parametrize(("subagents", "stem"), [(False, "review-inline"), (True, "review-delegated")])
def test_the_review_variant_follows_the_backend(
    repo: Path, tmp_path: Path, subagents: bool, stem: str
) -> None:
    story = _story(repo)
    agent = _Agent([verdict("story")])

    drive(
        PMReview(stage="story", subject=story, repo_dir=str(repo)),
        _env(tmp_path, agent, subagents=subagents),
    )

    assert dict(agent.calls) == {stem: 1}
    assert [angle["name"] for angle in agent.args[0]["angles"]] == [
        angle.name for angle in ANGLES["story"]
    ]


def test_an_unknown_stage_fails_before_any_turn(repo: Path, tmp_path: Path) -> None:
    agent = _Agent([])

    with pytest.raises(WorkflowFailed, match="no angles"):
        drive(PMReview(stage="nope", repo_dir=str(repo)), _env(tmp_path, agent))

    assert not agent.calls


def test_a_receipt_is_current_only_for_its_stage_and_digest(tmp_path: Path) -> None:
    assert not pm_receipt_current(tmp_path, "story", "abc")

    write_pm_receipt(tmp_path, "story", "abc")

    assert pm_receipt_current(tmp_path, "story", "abc")
    assert not pm_receipt_current(tmp_path, "story", "other")
    assert not pm_receipt_current(tmp_path, "story-split", "abc")
    (tmp_path / RECEIPT_NAME).write_text("not json", encoding="utf-8")
    assert not pm_receipt_current(tmp_path, "story", "abc")


def test_an_answer_reply_needs_its_text_and_an_amendment_its_reason() -> None:
    accepts(Answer(kind="answered", answer="sign in first"))
    accepts(Answer(kind="amendment", reason="the milestone must change"))
    with pytest.raises(ValueError):
        accepts(Answer(kind="answered"))
    with pytest.raises(ValueError):
        accepts(Answer(kind="amendment"))


def test_the_retry_note_names_the_question_and_who_answered() -> None:
    note = note_for("which first?", "sign-in", "PM")

    assert note == "You asked: which first?\nThe PM answers: sign-in"


def test_a_pm_answer_is_kept_in_the_ledger(repo: Path, tmp_path: Path) -> None:
    write_milestone(repo)
    agent = _Agent([answer("sign-in first")])

    result = drive(
        GapAnswer(question="which first?", asker="epic-split", repo_dir=str(repo)),
        _env(tmp_path, agent),
    )

    assert isinstance(result, GapAnswered)
    assert (result.kind, result.by, result.answer) == ("answered", "pm", "sign-in first")
    ledger = repo / "docs/milestones/account-access/grills/pm.md"
    text = ledger.read_text(encoding="utf-8")
    assert "which first?" in text
    assert "sign-in first" in text


def test_an_amendment_waits_on_the_operator_and_records_the_human_answer(
    repo: Path, tmp_path: Path
) -> None:
    write_milestone(repo)
    agent = _Agent([amendment("the milestone is silent")])
    seen: list[str] = []

    def human(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text(encoding="utf-8"))
        path.write_text(seen[-1] + "\nRecovery ships first.\n", encoding="utf-8")

    with patch.object(pyflow_park, "wait_for_answer", human):
        result = drive(
            GapAnswer(question="which first?", asker="story-split", repo_dir=str(repo)),
            _env(tmp_path, agent),
        )

    assert isinstance(result, GapAnswered)
    assert (result.kind, result.by) == ("amendment", "human")
    assert "Recovery ships first." in result.answer
    assert "the milestone is silent" in seen[0]
    ledger = repo / "docs/milestones/account-access/grills/pm.md"
    assert "Recovery ships first." in ledger.read_text(encoding="utf-8")
    assert agent.calls == {"answer": 1}


def test_an_empty_question_fails_before_any_turn(repo: Path, tmp_path: Path) -> None:
    agent = _Agent([])

    with pytest.raises(WorkflowFailed, match="question"):
        drive(GapAnswer(asker="story-split", repo_dir=str(repo)), _env(tmp_path, agent))

    assert not agent.calls


def test_the_receipt_file_is_plain_json(tmp_path: Path) -> None:
    path = write_pm_receipt(tmp_path, "story", "abc")

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "stage": "story",
        "status": "passed",
        "digest": "abc",
    }
