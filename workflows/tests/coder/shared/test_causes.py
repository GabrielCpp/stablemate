"""One cause, one owner: the judge, the word rule, the filing, consolidation and ownership."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path

import pytest
from workhorse import worklist as wl
from workhorse.runner.backends import claude as claude_backend

from workhorse_workflows.coder.shared import causes, work
from workhorse_workflows.coder.shared.judge import (
    JUDGE_PROFILE,
    Question,
    RuleJudge,
    Tiered,
    accepting,
    answer_of,
    judge_args,
)
from workhorse_workflows.coder.shared.schemas.judge import Ruling

HIDE = "Hide tabs/download when calculation yields zero stages"
HIDE_AND = "Hide tabs and download when calculation yields zero stages"
UNIQUE = "Guarantee unique report-panel names"
VERIFY = "Declare verify: checks for #loaded and #banks-open states"
STATUS = "Reconcile story.md Implementation Status"
EMPTY = "AC 8 says the user sees the empty state instead of report tabs when a project has no input rows."
EPIC = "epic-1"
LOG = logging.getLogger("test-causes")


class _Judge:
    """A judge that answers from a script and records what it was asked."""

    def __init__(self, answers: Mapping[str, str] | None = None, *, only: str = "") -> None:
        self.answers = dict(answers or {})
        self.only = only
        self.asked: list[Question] = []

    def rule(self, question: Question) -> Ruling:
        self.asked.append(question)
        if self.only and question.kind != self.only:
            return Ruling()
        return Ruling(answers={k: v for k, v in self.answers.items() if k in question.subjects})


class _Everything:
    """A judge that maps every subject to one answer."""

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.asked: list[Question] = []

    def rule(self, question: Question) -> Ruling:
        self.asked.append(question)
        return Ruling(answers=dict.fromkeys(question.subjects, self.answer))


@pytest.fixture
def w(tmp_path: Path) -> wl.WorkList:
    return work.worklist(tmp_path / "run")


def _stories(w: wl.WorkList, *slugs: str, done: tuple[str, ...] = ()) -> None:
    entries = [{"slug": slug, "epic": EPIC, "id": slug.upper()} for slug in slugs]
    work.file(w, work.story_items(entries), by="launch")
    if done:
        w.settle(list(done), work.DONE, work.STORY)


def _follow_up(w: wl.WorkList, parent: str, title: str, reason: str = "r") -> wl.WorkItem:
    item = work.find(w, parent)
    assert item is not None
    (made,) = work.follow_up_items(w, item, [{"title": title, "reason": reason}])
    work.file(w, [made], by="dev")
    return made


def _finding(w: wl.WorkList, work_id: str, number: int, issue: str = EMPTY) -> wl.WorkItem:
    (made,) = work.file(
        w, work.finding_items(work_id, "qa", number, [{"issue": issue, "target": "t"}]), by="qa"
    )
    return made


def _question(subjects: dict[str, str], context: dict[str, str]) -> Question:
    return causes.cause_question(subjects, context)


def test_the_word_rule_reads_through_spelling_and_not_through_a_different_cause() -> None:
    assert causes.words(HIDE) == causes.words(HIDE_AND)
    assert causes.words(UNIQUE) != causes.words(HIDE)
    ruling = causes.cause_rule(_question({"r1": HIDE_AND, "r2": UNIQUE}, {"c1": HIDE}))
    assert ruling.answers == {"r1": "c1"}


def test_tiered_asks_the_second_judge_only_for_what_the_first_left() -> None:
    first = _Judge({"r1": "c1"})
    then = _Judge({"r2": "new"})
    question = _question({"r1": HIDE, "r2": UNIQUE}, {"c1": HIDE})

    ruling = Tiered(first, then).rule(question)

    assert ruling.answers == {"r1": "c1", "r2": "new"}
    assert [list(q.subjects) for q in then.asked] == [["r2"]]
    assert list(question.subjects) == ["r1", "r2"]


def test_tiered_does_not_ask_the_second_judge_when_nothing_is_left() -> None:
    then = _Judge()
    question = _question({"r1": HIDE_AND}, {"c1": HIDE})

    ruling = Tiered(RuleJudge({"cause": causes.cause_rule}), then).rule(question)

    assert ruling.answers == {"r1": "c1"}
    assert then.asked == []


def test_the_judge_turn_has_no_tool_to_spend_its_one_step_on() -> None:
    """A judge with file tools wrote its answer to a scratch file, and the turn ended on max turns with no ruling."""
    assert JUDGE_PROFILE.steps == 1
    assert claude_backend._tool_flags(JUDGE_PROFILE, "/work/app") == ["--tools", "", "--strict-mcp-config"]


def test_an_unanswered_subject_takes_the_default() -> None:
    question = _question({"r1": HIDE}, {"c1": UNIQUE})
    assert answer_of(question, Ruling(), "r1") == "new"
    assert answer_of(question, Ruling(answers={"r1": "c1"}), "r1") == "c1"


def test_the_reply_check_rejects_an_unknown_answer_and_an_unknown_subject() -> None:
    check = accepting(_question({"r1": HIDE}, {"c1": UNIQUE}))
    check(Ruling(answers={"r1": "c1"}))
    with pytest.raises(ValueError, match="allowed answer"):
        check(Ruling(answers={"r1": "c9"}))
    with pytest.raises(ValueError, match="subjects"):
        check(Ruling(answers={"r9": "c1"}))


def test_the_prompt_arguments_carry_every_subject_and_context_text() -> None:
    question = _question({"r1": EMPTY}, {"c1": HIDE, "c2": UNIQUE})

    args = judge_args(question)

    assert EMPTY in args["subjects"]
    assert HIDE in args["context"] and UNIQUE in args["context"]
    assert "`c1`" in args["answers"] and "`new`" in args["answers"]
    assert args["default"] == "new"


def test_a_cause_asked_with_no_known_cause_asks_no_judge() -> None:
    judge = _Judge()
    assert causes.same_causes(judge, {"r1": HIDE}, {}) == {"r1": "new"}
    assert judge.asked == []


def test_four_rounds_of_one_finding_leave_one_open_and_three_merged(w: wl.WorkList) -> None:
    _stories(w, "story-a")
    judge = Tiered(RuleJudge({"cause": causes.cause_rule}), _Judge())
    for number in (1, 2, 3, 4):
        causes.file_findings(
            judge, w, "story-a", "qa", number, [{"issue": EMPTY, "target": "t"}], by="qa"
        )

    opened = work.open_findings(w, "story-a")
    merged = [it for it in w.items(work.FINDING) if it.status == work.MERGED]

    assert [it.id for it in opened] == ["story-a/qa-4.1"]
    assert sorted(it.id for it in merged) == ["story-a/qa-1.1", "story-a/qa-2.1", "story-a/qa-3.1"]
    assert [(it.id, it.payload["same_as"]) for it in sorted(merged, key=lambda x: x.id)] == [
        ("story-a/qa-1.1", "story-a/qa-2.1"),
        ("story-a/qa-2.1", "story-a/qa-3.1"),
        ("story-a/qa-3.1", "story-a/qa-4.1"),
    ]
    assert work.next_round(w, "story-a", "qa") == 5


def test_consolidation_keeps_one_follow_up_per_cause_and_the_active_one(w: wl.WorkList) -> None:
    _stories(w, "story-a")
    for title in (HIDE, HIDE_AND, HIDE, HIDE_AND):
        _follow_up(w, "story-a", title, f"reason {len(w.items(work.FOLLOW_UP))}")
    for title in (UNIQUE, VERIFY, STATUS):
        for n in range(4):
            _follow_up(w, "story-a", title, f"reason {n}")
    assert len(w.items(work.FOLLOW_UP)) == 16
    active = next(it for it in w.items(work.FOLLOW_UP) if it.payload["title"] == HIDE_AND)
    w.settle([active.id], work.ACTIVE, work.FOLLOW_UP)

    pruned = causes.consolidate(w, LOG)

    left = w.items(work.FOLLOW_UP)
    assert len(left) == 4 and len(pruned) == 12
    assert active.id in {it.id for it in left}
    assert {causes.words(str(it.payload["title"])) for it in left} == {
        causes.words(t) for t in (HIDE, UNIQUE, VERIFY, STATUS)
    }


def _escaped_setup(w: wl.WorkList) -> wl.WorkItem:
    _stories(w, "story-a", "story-b", done=("story-a",))
    for number in (1, 2, 3, 4):
        _finding(w, "story-a", number)
    return _follow_up(w, "story-b", HIDE)


def test_findings_left_open_on_a_done_story_go_to_the_follow_up_that_owns_the_cause(
    w: wl.WorkList,
) -> None:
    target = _escaped_setup(w)
    answers = {f"story-a/qa-{n}.1": target.id for n in (1, 2, 3, 4)}

    causes.consolidate(w, LOG)
    moved = causes.own(_Judge(answers), w, LOG)

    assert moved == 4
    assert {it.payload["work_id"] for it in w.items(work.FINDING)} == {target.id}
    assert len(work.open_findings(w, target.id)) == 1
    assert work.open_findings(w, "story-a") == []
    assert [it.id for it in work.escapes(w, "story-a")] == [target.id]


def test_findings_no_follow_up_owns_file_one_follow_up_under_the_done_story(
    w: wl.WorkList,
) -> None:
    _escaped_setup(w)

    moved = causes.own(Tiered(RuleJudge({"cause": causes.cause_rule}), _Everything("new")), w, LOG)

    owners = [it for it in w.items(work.FOLLOW_UP) if it.payload.get("parent") == "story-a"]
    assert moved == 4
    assert len(owners) == 1
    assert owners[0].payload["escaped_from"] == "story-a"
    assert {it.payload["work_id"] for it in w.items(work.FINDING)} == {owners[0].id}
    assert len(work.open_findings(w, owners[0].id)) == 1
    assert work.open_findings(w, "story-a") == []


def test_a_commit_check_places_findings_without_filing_a_follow_up(w: wl.WorkList) -> None:
    _stories(w, "story-a")
    _finding(w, "story-a", 1)

    moved = causes.own(_Everything("new"), w, LOG, owners={"story-a"}, file_new=False)

    assert moved == 0
    assert len(work.open_findings(w, "story-a")) == 1
    assert w.items(work.FOLLOW_UP) == []
