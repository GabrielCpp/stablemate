"""Directly author one explicit story without selecting, branching, or committing."""
from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from workhorse.pyflow import Continue, Done, Workflow
from workhorse_workflows.author.pm import MAX_ANSWERS, GapAnswer, PMReview
from workhorse_workflows.author.shared.nodes import (
    check_story_grounding,
    load_config,
    record_attempt,
    validate_story,
)
from workhorse_workflows.author.shared.schemas import Config, MockupResult, WriteStoryResult
from workhorse_workflows.author.story_author.nodes import (
    check_mockup_needed,
    check_story_feedback,
    prepare_story,
)
from workhorse_workflows.author.story_author.schemas import StoryAuthorDone, StoryTarget
from workhorse_workflows.kit.telemetry import counter_labels

MAX_REWORKS = 3


class StoryAuthor(Workflow):
    """Run the current per-story author pipeline for one caller-selected story."""

    epic: str = ""
    story: str = ""
    feedback_dir: str = ""
    note: str = ""

    BUDGET_LABELS: ClassVar[tuple[str, ...]] = ("reworks", "answers")

    def setup(self) -> Config:
        """Resolve config only; direct story authoring never creates a branch."""
        return self.call(load_config, mode="story-author")

    def labels(self) -> dict[str, str]:
        return {"work_id": self.story, "epic": self.epic, "progress": "authoring one story"}

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        return self.labels() | counter_labels(params, "story_author", self.BUDGET_LABELS)

    def _abs(self, relative: str) -> Path:
        return Path(self.ctx.repo_root) / relative

    def _args(self, target: StoryTarget, mockup: str, **extra: str) -> dict[str, str]:
        return {
            "epic": target.epic,
            "story_path": target.story_path,
            "story_slug": target.story,
            "story_dir": target.story_dir,
            "services_dir": self.ctx.services_dir,
            "mockup_path": mockup,
            "ledger": self.ctx.pm_ledger,
            **extra,
        }

    def _blocked(
        self, target: StoryTarget, mockup: str, notes: str, reworks: int, answers: int
    ) -> Done:
        self.logger.warning("parking story '%s': %s", target.story, notes)
        return Done(
            StoryAuthorDone(
                status="blocked",
                epic=target.epic,
                story=target.story,
                story_path=target.story_path,
                mockup=mockup,
                notes=notes,
                reworks=reworks,
                answers=answers,
            )
        )

    def start(self) -> Continue:
        target = self.call(prepare_story, self.epic, self.story)
        gate = self.call(check_mockup_needed, target.story)
        if gate.required:
            return Continue(gate, self.design_mockup, target=target)
        return Continue(gate, self.write_story, target=target)

    def design_mockup(self, target: StoryTarget) -> Continue | Done:
        result = self.agent(
            "story_author/prompts/design-mockup.md",
            returns=MockupResult,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "epic": target.epic,
                "story_slug": target.story,
                "story_dir": target.story_dir,
                "services_dir": self.ctx.services_dir,
                "epics_dir": self.ctx.epics_dir,
                "milestone_mockups_dir": self.ctx.milestone_mockups_dir,
            },
        )
        if result.status == "failed" or not (
            result.mockup and self._abs(result.mockup).is_file()
        ):
            reason = result.notes or "the mockup turn produced no mockup file"
            self.logger.warning(
                "blocking story '%s': a story with a UI service cannot be written without a "
                "mockup: %s",
                target.story,
                reason,
            )
            return Done(
                StoryAuthorDone(
                    status="blocked",
                    epic=target.epic,
                    story=target.story,
                    story_path=target.story_path,
                    notes=f"no mockup for a story with a UI service: {reason}",
                )
            )
        return Continue(result, self.write_story, target=target, mockup=result.mockup)

    def write_story(
        self,
        target: StoryTarget,
        mockup: str = "",
        reworks: int = 0,
        answers: int = 0,
        note: str = "",
        prior: str = "",
    ) -> Continue | Done:
        self.logger.info("authoring %s", target.story, extra={"activity": True})
        result = self.agent(
            "story_author/prompts/write-story.md",
            returns=WriteStoryResult,
            power="high",
            cwd=self.ctx.repo_root,
            args=self._args(
                target,
                mockup,
                note="\n\n".join(part for part in (self.note, note) if part),
            ),
        )
        if result.status == "blocked":
            return self._ask(
                result.notes, "write", target, mockup, "", reworks, answers, prior
            )
        return Continue(
            result,
            self.check_story,
            target=target,
            mockup=mockup,
            reworks=reworks,
            answers=answers,
            prior=prior,
        )

    def check_story(
        self,
        target: StoryTarget,
        mockup: str = "",
        reworks: int = 0,
        answers: int = 0,
        prior: str = "",
    ) -> Continue | Done:
        structure = self.call(validate_story, target.story_dir)
        if not structure.ok:
            return self._rework(
                structure, structure.errors, target, mockup, reworks, answers, prior
            )
        grounding = self.call(
            check_story_grounding,
            target.story_dir,
            target.epic_dir,
            self.ctx.services_dir,
        )
        if not grounding.ok:
            return self._rework(
                grounding, grounding.errors, target, mockup, reworks, answers, prior
            )
        return Continue(
            grounding,
            self.review,
            target=target,
            mockup=mockup,
            reworks=reworks,
            answers=answers,
            prior=prior,
        )

    def review(
        self,
        target: StoryTarget,
        mockup: str = "",
        reworks: int = 0,
        answers: int = 0,
        prior: str = "",
    ) -> Continue | Done:
        verdict = self.handoff(
            PMReview,
            stage="story",
            subject=target.story_path,
            epic=target.epic,
            prior=prior,
        )
        if verdict.passed:
            return Continue(
                verdict,
                self.story_feedback,
                target=target,
                mockup=mockup,
                reworks=reworks,
                answers=answers,
            )
        return self._rework(
            verdict, verdict.notes, target, mockup, reworks, answers, verdict.notes
        )

    def _rework(
        self,
        result: object,
        notes: str,
        target: StoryTarget,
        mockup: str,
        reworks: int,
        answers: int,
        prior: str,
    ) -> Continue | Done:
        if reworks >= MAX_REWORKS:
            return self._blocked(target, mockup, notes, reworks, answers)
        return Continue(
            result,
            self.rework_story,
            target=target,
            mockup=mockup,
            notes=notes,
            reworks=reworks,
            answers=answers,
            prior=prior,
        )

    def _ask(
        self,
        question: str,
        phase: str,
        target: StoryTarget,
        mockup: str,
        notes: str,
        reworks: int,
        answers: int,
        prior: str,
    ) -> Continue | Done:
        if answers >= MAX_ANSWERS:
            return self._blocked(target, mockup, question, reworks, answers)
        return Continue(
            None,
            self.ask_pm,
            question=question,
            phase=phase,
            target=target,
            mockup=mockup,
            notes=notes,
            reworks=reworks,
            answers=answers,
            prior=prior,
        )

    def rework_story(
        self,
        target: StoryTarget,
        notes: str,
        mockup: str = "",
        reworks: int = 0,
        answers: int = 0,
        note: str = "",
        prior: str = "",
    ) -> Continue | Done:
        attempts = self.call(
            record_attempt,
            f"{target.story_dir.rstrip('/')}/attempts.md",
            str(reworks),
            notes,
        )
        result = self.agent(
            "story_author/prompts/rework-story.md",
            returns=WriteStoryResult,
            power="high",
            cwd=self.ctx.repo_root,
            args=self._args(
                target,
                mockup,
                validation_errors=notes,
                prior_attempts=attempts.prior_attempts,
                note=note,
            ),
        )
        if result.status == "blocked":
            return self._ask(
                result.notes, "rework", target, mockup, notes, reworks, answers, prior
            )
        return Continue(
            result,
            self.check_story,
            target=target,
            mockup=mockup,
            reworks=reworks + 1,
            answers=answers,
            prior=prior,
        )

    def ask_pm(
        self,
        question: str,
        phase: str,
        target: StoryTarget,
        mockup: str = "",
        notes: str = "",
        reworks: int = 0,
        answers: int = 0,
        prior: str = "",
    ) -> Continue:
        answer = self.handoff(GapAnswer, question=question, asker="story-author")
        if phase == "write":
            return Continue(
                answer,
                self.write_story,
                target=target,
                mockup=mockup,
                reworks=reworks,
                answers=answers + 1,
                note=answer.note,
                prior=prior,
            )
        return Continue(
            answer,
            self.rework_story,
            target=target,
            notes=notes,
            mockup=mockup,
            reworks=reworks,
            answers=answers + 1,
            note=answer.note,
            prior=prior,
        )

    def story_feedback(
        self,
        target: StoryTarget,
        mockup: str = "",
        reworks: int = 0,
        answers: int = 0,
    ) -> Continue | Done:
        feedback = self.call(check_story_feedback, self.feedback_dir or str(self.run_dir))
        if feedback.present:
            return Continue(
                feedback,
                self.apply_feedback,
                target=target,
                mockup=mockup,
                notes=feedback.content,
                reworks=reworks,
                answers=answers,
            )
        return Done(
            StoryAuthorDone(
                epic=target.epic,
                story=target.story,
                story_path=target.story_path,
                mockup=mockup,
                reworks=reworks,
                answers=answers,
            )
        )

    def apply_feedback(
        self,
        target: StoryTarget,
        notes: str,
        mockup: str = "",
        reworks: int = 0,
        answers: int = 0,
    ) -> Continue:
        result = self.agent(
            "story_author/prompts/rework-story.md",
            returns=WriteStoryResult,
            power="high",
            cwd=self.ctx.repo_root,
            args=self._args(
                target, mockup, validation_errors="", operator_feedback=notes
            ),
        )
        return Continue(
            result,
            self.check_story,
            target=target,
            mockup=mockup,
            reworks=reworks,
            answers=answers,
        )


__all__ = ["StoryAuthor"]
