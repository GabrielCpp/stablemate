"""Directly author one explicit story without selecting, branching, or committing."""
from __future__ import annotations

from pathlib import Path

from workhorse.pyflow import Continue, Done, Workflow
from workhorse_workflows.author.draft import DraftDone, DraftLoop
from workhorse_workflows.author.shared.nodes import load_config
from workhorse_workflows.author.shared.schemas import Config, MockupResult, WriteStoryResult
from workhorse_workflows.author.story_author.nodes import (
    check_mockup_needed,
    check_story_feedback,
    prepare_story,
)
from workhorse_workflows.author.story_author.schemas import StoryAuthorDone, StoryTarget


class StoryAuthor(Workflow):
    """Run the current per-story author pipeline for one caller-selected story."""

    epic: str = ""
    story: str = ""
    feedback_dir: str = ""
    note: str = ""

    def setup(self) -> Config:
        """Resolve config only; direct story authoring never creates a branch."""
        return self.call(load_config, mode="story-author")

    def labels(self) -> dict[str, str]:
        return {"work_id": self.story, "epic": self.epic, "progress": "authoring one story"}

    def _abs(self, relative: str) -> Path:
        return Path(self.ctx.repo_root) / relative

    def _args(self, target: StoryTarget, mockup: str, **extra: str) -> dict[str, str]:
        return {
            "epic": target.epic,
            "story_path": target.story_path,
            "story_slug": target.story,
            "story_id": target.story_id,
            "story_dir": target.story_dir,
            "mockup_path": mockup,
            "ledger": self.ctx.pm_ledger,
            **extra,
        }

    def _done(self, target: StoryTarget, mockup: str, spent: DraftDone) -> StoryAuthorDone:
        return StoryAuthorDone(
            status="blocked" if spent.status == "blocked" else "authored",
            epic=target.epic,
            story=target.story,
            story_path=target.story_path,
            mockup=mockup,
            notes=spent.notes,
            reworks=spent.reworks,
            answers=spent.answers,
        )

    def start(self) -> Continue:
        target = self.call(prepare_story, self.epic, self.story)
        gate = self.call(check_mockup_needed, target.story_id)
        if gate.required:
            return Continue(gate, self.design_mockup, target=target).because("the story changes a UI service")
        return Continue(gate, self.draft, target=target).because("no mockup needed")

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
            ).because("no mockup")
        return Continue(result, self.draft, target=target, mockup=result.mockup).because("mockup drawn")

    def draft(self, target: StoryTarget, mockup: str = "", written: bool = False) -> Continue | Done:
        """Write the story and loop it through the checks and the PM until it passes or stays blocked."""
        self.logger.info("authoring %s", target.story, extra={"activity": True})
        spent = self.handoff(
            DraftLoop,
            kind="story",
            subject=target.story_path,
            epic=target.epic,
            epic_dir=target.epic_dir,
            story_dir=target.story_dir,
            args=self._args(target, mockup),
            note=self.note,
            written=written,
        )
        if spent.status == "blocked":
            self.logger.warning("parking story '%s': %s", target.story, spent.notes)
            return Done(self._done(target, mockup, spent)).because("the story stayed blocked")
        return Continue(spent, self.story_feedback, target=target, mockup=mockup, spent=spent).because(
            "the PM passed it"
        )

    def story_feedback(self, target: StoryTarget, spent: DraftDone, mockup: str = "") -> Continue | Done:
        """Apply the operator's feedback when they left some, and check the story again."""
        feedback = self.call(check_story_feedback, self.feedback_dir or str(self.run_dir))
        if not feedback.present:
            return Done(self._done(target, mockup, spent)).because("no operator feedback")
        self.agent(
            "story_author/prompts/rework-story.md",
            returns=WriteStoryResult,
            power="high",
            cwd=self.ctx.repo_root,
            args=self._args(target, mockup, findings="", operator_feedback=feedback.content),
        )
        return Continue(feedback, self.draft, target=target, mockup=mockup, written=True).because(
            "operator feedback applied"
        )


__all__ = ["StoryAuthor"]
