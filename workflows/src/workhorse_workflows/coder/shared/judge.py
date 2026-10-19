"""Judgment: a closed question put to a rule, to one tool-less model call, or to a rule first."""
from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from pydantic import BaseModel
from workhorse.runner.backends import AgentProfile

from workhorse_workflows.coder.shared.schemas.judge import Ruling
from workhorse_workflows.coder.shared.schemas.render import schema_block

JUDGE_PROFILE = AgentProfile(name="coder-judge", confined=True, steps=1)


class Question(BaseModel):
    """One closed question: what to answer, about which subjects, from which answers."""

    kind: str
    ask: str
    subjects: dict[str, str]
    context: dict[str, str]
    answers: tuple[str, ...]
    default: str


class Judge(Protocol):
    """Anything that can rule on a question."""

    def rule(self, question: Question) -> Ruling:
        """Answer the subjects it can, and leave the rest out."""
        ...


def answer_of(question: Question, ruling: Ruling, subject: str) -> str:
    """The ruling's answer for `subject`, or the question's default when it gave none."""
    return ruling.answers.get(subject, question.default)


def judge_args(question: Question) -> dict[str, Any]:
    """The template arguments `shared/prompts/judge.md` takes for one question."""
    return {
        "kind": question.kind,
        "ask": question.ask,
        "answers": ", ".join(f"`{answer}`" for answer in question.answers),
        "default": question.default,
        "subjects": json.dumps(question.subjects, indent=2, ensure_ascii=False),
        "context": json.dumps(question.context, indent=2, ensure_ascii=False),
        "result_schema": schema_block(Ruling),
    }


def accepting(question: Question) -> Callable[[Ruling], None]:
    """The check a reply must pass: every subject is one the question named, every answer one it allows."""

    def check(ruling: Ruling) -> None:
        for subject, answer in ruling.answers.items():
            if subject not in question.subjects:
                raise ValueError(f"{subject!r} is not one of the subjects to answer about")
            if answer not in question.answers:
                raise ValueError(
                    f"{answer!r} is not an allowed answer for {subject!r}; "
                    f"the allowed answers are {list(question.answers)}"
                )

    return check


class RuleJudge:
    """Answers by the fixed rule for the question's kind, and only what that rule decides."""

    def __init__(self, rules: Mapping[str, Callable[[Question], Ruling]]) -> None:
        self.rules = dict(rules)

    def rule(self, question: Question) -> Ruling:
        """The rule's ruling, or an empty one when the kind has no rule."""
        rule = self.rules.get(question.kind)
        return rule(question) if rule is not None else Ruling()


class ReadingJudge:
    """Reads the question once, in the one model call its flow makes for it."""

    def __init__(self, read: Callable[[Question], Ruling]) -> None:
        self.read = read

    def rule(self, question: Question) -> Ruling:
        """One model call over the question's subjects, or an empty ruling when it has none."""
        return self.read(question) if question.subjects else Ruling()


class Tiered:
    """Asks `first`, then asks `then` only about the subjects `first` left unanswered."""

    def __init__(self, first: Judge, then: Judge) -> None:
        self.first = first
        self.then = then

    def rule(self, question: Question) -> Ruling:
        """The two rulings merged, with no second call when the first answered everything."""
        ruling = self.first.rule(question)
        left = {k: v for k, v in question.subjects.items() if k not in ruling.answers}
        if not left:
            return ruling
        narrowed = question.model_copy(update={"subjects": left})
        return Ruling(answers=ruling.answers | self.then.rule(narrowed).answers)


__all__ = [
    "JUDGE_PROFILE",
    "Judge",
    "Question",
    "ReadingJudge",
    "Ruling",
    "RuleJudge",
    "Tiered",
    "accepting",
    "answer_of",
    "judge_args",
]
