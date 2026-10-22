"""Standalone story-split and PM review convergence for one epic."""
from __future__ import annotations

from typing import Any, ClassVar

from workhorse.pyflow import Continue, Done, Workflow, WorkflowFailed
from workhorse_workflows.author.pm import MAX_ANSWERS, GapAnswer, PMReview
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.nodes import load_config, validate_coverage
from workhorse_workflows.author.shared.schemas import Config, StorySplit
from workhorse_workflows.author.story_split.nodes import derive_story_services
from workhorse_workflows.author.story_split.schemas import StorySplitDone
from workhorse_workflows.kit.telemetry import counter_labels

MAX_REWORKS = 3


class StorySplitFlow(Workflow):
    """Create and accept the story graph for one explicitly named epic."""

    epic: str = ""
    note: str = ""

    BUDGET_LABELS: ClassVar[tuple[str, ...]] = ("reworks", "answers")

    def setup(self) -> Config:
        return self.call(load_config, mode="story-split")

    def labels(self) -> dict[str, str]:
        return {"work_id": self.epic, "epic": self.epic, "progress": "splitting stories"}

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        return self.labels() | counter_labels(params, "story_split", self.BUDGET_LABELS)

    def _epic_dir(self) -> str:
        return paths.epic_dir(self.ctx.repo_root, self.epic)

    def _blocked(self, notes: str, reworks: int, answers: int) -> Done:
        self.logger.warning("the story split of %s stays blocked: %s", self.epic, notes)
        return Done(
            StorySplitDone(
                status="blocked",
                epic=self.epic,
                epic_dir=self._epic_dir(),
                notes=notes,
                reworks=reworks,
                answers=answers,
            )
        )

    def start(self) -> Continue:
        if not self.epic.strip():
            raise WorkflowFailed(
                "story-split needs exactly one non-empty 'epic'",
                failure_class="story-split-missing-epic",
            )
        return Continue(None, self.split_stories)

    def split_stories(
        self,
        reworks: int = 0,
        answers: int = 0,
        rework_notes: str = "",
        note: str = "",
        prior: str = "",
    ) -> Continue | Done:
        result = self.agent(
            "story_split/prompts/split-stories.md",
            returns=StorySplit,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "epic": self.epic,
                "epic_dir": self._epic_dir(),
                "rework_notes": rework_notes,
                "note": "\n\n".join(part for part in (self.note, note) if part),
                "ledger": self.ctx.pm_ledger,
            },
        )
        if result.status in {"blocked", "standoff"}:
            if answers >= MAX_ANSWERS:
                return self._blocked(result.notes, reworks, answers)
            return Continue(
                result,
                self.ask_pm,
                question=result.notes,
                reworks=reworks,
                answers=answers,
                rework_notes=rework_notes,
                prior=prior,
            )
        return Continue(result, self.check_coverage, reworks=reworks, answers=answers, prior=prior)

    def check_coverage(
        self, reworks: int = 0, answers: int = 0, prior: str = ""
    ) -> Continue | Done:
        self.call(derive_story_services, self.epic)
        mechanical = self.call(validate_coverage, self._epic_dir(), require_authored=False)
        if not mechanical.ok:
            return self._rework(mechanical, mechanical.errors, reworks, answers, prior)
        return Continue(mechanical, self.review, reworks=reworks, answers=answers, prior=prior)

    def review(self, reworks: int = 0, answers: int = 0, prior: str = "") -> Continue | Done:
        verdict = self.handoff(
            PMReview,
            stage="story-split",
            subject=self._epic_dir(),
            prior=prior,
        )
        if verdict.passed:
            return Done(
                StorySplitDone(
                    epic=self.epic,
                    epic_dir=self._epic_dir(),
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
            result,
            self.split_stories,
            reworks=reworks + 1,
            answers=answers,
            rework_notes=notes,
            prior=prior,
        )

    def ask_pm(
        self,
        question: str,
        reworks: int = 0,
        answers: int = 0,
        rework_notes: str = "",
        prior: str = "",
    ) -> Continue:
        answer = self.handoff(GapAnswer, question=question, asker="story-split")
        return Continue(
            answer,
            self.split_stories,
            reworks=reworks,
            answers=answers + 1,
            rework_notes=rework_notes,
            note=answer.note,
            prior=prior,
        )


__all__ = ["StorySplitFlow", "MAX_REWORKS"]
