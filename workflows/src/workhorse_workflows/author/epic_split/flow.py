"""Split one milestone into an ordered list of epic skeletons."""
from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from workhorse.pyflow import Continue, Done, Workflow
from workhorse_workflows.author.epic_split.nodes import prepare_epic_split, validate_epic_split
from workhorse_workflows.author.epic_split.schemas import (
    EpicSplitContext,
    EpicSplitDone,
    EpicSplitResult,
)
from workhorse_workflows.author.pm import MAX_ANSWERS, GapAnswer, PMReview
from workhorse_workflows.kit.telemetry import counter_labels

MAX_REWORKS = 3


class EpicSplit(Workflow):
    """The epic-skeleton boundary; epic prose, seeds, stories, and delivery are unreachable."""

    note: str = ""

    BUDGET_LABELS: ClassVar[tuple[str, ...]] = ("reworks", "answers")

    def setup(self) -> EpicSplitContext:
        return self.call(prepare_epic_split)

    def labels(self) -> dict[str, str]:
        return {"work_id": Path(self.ctx.milestone_path).parent.name}

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        return self.labels() | counter_labels(params, "epic_split", self.BUDGET_LABELS)

    def _split_args(self, review_notes: str = "", note: str = "") -> dict[str, str]:
        return {
            "milestone": self.ctx.milestone_path,
            "epics_dir": self.ctx.epics_dir,
            "review_notes": review_notes,
            "note": "\n\n".join(part for part in (self.note, note) if part),
            "ledger": self.ctx.pm_ledger,
        }

    def _blocked(self, notes: str, reworks: int, answers: int) -> Done:
        self.logger.warning("the epic split stays blocked: %s", notes)
        return Done(
            EpicSplitDone(
                status="blocked",
                milestone_path=self.ctx.milestone_path,
                notes=notes,
                reworks=reworks,
                answers=answers,
            )
        )

    def _ask(
        self,
        question: str,
        phase: str,
        notes: str,
        reworks: int,
        answers: int,
        prior: str,
    ) -> Continue | Done:
        if answers >= MAX_ANSWERS:
            return self._blocked(question, reworks, answers)
        return Continue(
            None,
            self.ask_pm,
            question=question,
            phase=phase,
            notes=notes,
            reworks=reworks,
            answers=answers,
            prior=prior,
        )

    def start(self, note: str = "", answers: int = 0) -> Continue | Done:
        result = self.agent(
            "epic_split/prompts/split-epics.md",
            returns=EpicSplitResult,
            power="high",
            cwd=self.ctx.repo_root,
            args=self._split_args(note=note),
        )
        if result.status == "blocked":
            return self._ask(result.notes, "split", "", 0, answers, "")
        return Continue(result, self.check, answers=answers)

    def check(self, reworks: int = 0, answers: int = 0, prior: str = "") -> Continue | Done:
        validation = self.call(validate_epic_split, self.ctx)
        if not validation.ok:
            return self._rework(validation, validation.errors, reworks, answers, prior)
        return Continue(validation, self.review, reworks=reworks, answers=answers, prior=prior)

    def review(self, reworks: int = 0, answers: int = 0, prior: str = "") -> Continue | Done:
        verdict = self.handoff(
            PMReview,
            stage="epic-split",
            subject=self.ctx.milestone_path,
            prior=prior,
        )
        if verdict.passed:
            validation = self.call(validate_epic_split, self.ctx)
            return Done(
                EpicSplitDone(
                    milestone_path=validation.milestone_path,
                    ordered_epics=validation.ordered_epics,
                    reworks=reworks,
                    answers=answers,
                )
            )
        return self._rework(verdict, verdict.notes, reworks, answers, verdict.notes)

    def _rework(
        self, result: object, notes: str, reworks: int, answers: int, prior: str
    ) -> Continue | Done:
        if reworks >= MAX_REWORKS:
            return self._blocked(notes, reworks, answers)
        return Continue(
            result, self.rework, notes=notes, reworks=reworks, answers=answers, prior=prior
        )

    def rework(
        self,
        notes: str,
        note: str = "",
        reworks: int = 0,
        answers: int = 0,
        prior: str = "",
    ) -> Continue | Done:
        result = self.agent(
            "epic_split/prompts/rework-epic-split.md",
            returns=EpicSplitResult,
            power="high",
            cwd=self.ctx.repo_root,
            args=self._split_args(notes, note),
        )
        if result.status == "blocked":
            return self._ask(result.notes, "rework", notes, reworks, answers, prior)
        return Continue(result, self.check, reworks=reworks + 1, answers=answers, prior=prior)

    def ask_pm(
        self,
        question: str,
        phase: str,
        notes: str = "",
        reworks: int = 0,
        answers: int = 0,
        prior: str = "",
    ) -> Continue:
        answer = self.handoff(GapAnswer, question=question, asker="epic-split")
        if phase == "split":
            return Continue(answer, self.start, note=answer.note, answers=answers + 1)
        return Continue(
            answer,
            self.rework,
            notes=notes,
            note=answer.note,
            reworks=reworks,
            answers=answers + 1,
            prior=prior,
        )


__all__ = ["EpicSplit", "MAX_REWORKS"]
