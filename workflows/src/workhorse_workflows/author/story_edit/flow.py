"""Manual story graph edits, intentionally disconnected from the main author loop."""
from __future__ import annotations

from pathlib import Path

from workhorse.pyflow import Await, Continue, Done, Workflow, WorkflowFailed
from workhorse_workflows.author.nodes import (
    branch_author,
    check_story_grounding,
    commit_author,
    load_config,
    prune_bullet,
    record_attempt,
    remove_story,
    seed_story,
    validate_story,
    verify_integrity,
)
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.schemas import (
    AuditResult,
    MockupResult,
    RunContext,
    StoryMutation,
    WriteStoryResult,
)

MAX_REWORKS = 3


class StoryEdit(Workflow):
    """Add or remove one story without entering the full backlog authoring flow."""

    #: ``add`` authors one backlog bullet into an existing epic; ``remove`` deletes one story.
    action: str = "add"
    #: Add mode: the existing epic to append to.
    epic: str = ""
    #: Add mode: a backlog ``[id]`` or literal story request.
    bullet: str = ""
    #: Remove mode: the story slug to delete.
    story: str = ""
    #: Remove mode: allow deleting stories whose status is not ``Not started``.
    force: bool = False
    #: Optional author path overrides, same contract as the main author workflow.
    backlog: str = ""
    epics_dir: str = ""

    def setup(self) -> RunContext:
        cfg = self.call(load_config, self.backlog, self.epics_dir)
        branches = self.call(branch_author, str(self.run_dir), f"story-edit-{self.action}")
        return RunContext(
            **cfg.model_dump(),
            base_branch=branches.base_branch,
            author_branch=branches.author_branch,
        )

    def labels(self) -> dict[str, str]:
        work_id = self.story if self.action == "remove" else self.epic
        return {"work_id": work_id, "epic": self.epic, "progress": "manual story edit"}

    def _abs(self, rel: str) -> Path:
        return Path(self.ctx.repo_root) / rel

    def start(self) -> Continue:
        if self.action == "remove":
            result = self.call(remove_story, self.story, self.force)
            return Continue(result, self.check_remove_integrity, mutation=result)
        if self.action != "add":
            raise WorkflowFailed("story-edit action must be 'add' or 'remove'")

        seeded = self.call(seed_story, self.epic, self.epics_dir, self.bullet, self.backlog)
        return Continue(
            seeded,
            self.design_mockup,
            epic=self.epic,
            story_slug=seeded.story_slug,
            story_dir=seeded.story_dir,
            story_path=seeded.story_path,
        )

    def design_mockup(
        self,
        epic: str,
        story_slug: str,
        story_dir: str,
        story_path: str,
    ) -> Continue:
        result = self.agent(
            "prompts/design-mockup.md",
            returns=MockupResult,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "epic": epic,
                "story_slug": story_slug,
                "story_dir": story_dir,
                "features_dir": self.ctx.features_dir,
                "surface_manifest": self.ctx.surface_manifest,
                "mockup_dir": self.ctx.mockup_dir,
            },
        )
        return Continue(
            result,
            self.write_story,
            epic=epic,
            story_slug=story_slug,
            story_dir=story_dir,
            story_path=story_path,
            mockup=result.mockup,
        )

    def write_story(
        self,
        epic: str,
        story_slug: str,
        story_dir: str,
        story_path: str,
        mockup: str = "",
        reworks: int = 0,
    ) -> Continue | Await:
        result = self.agent(
            "prompts/write-story.md",
            returns=WriteStoryResult,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "epic": epic,
                "story_path": story_path,
                "story_slug": story_slug,
                "story_dir": story_dir,
                "features_dir": self.ctx.features_dir,
                "mockup_dir": self.ctx.mockup_dir,
                "mockup_path": mockup,
            },
        )
        if result.status == "blocked":
            context = paths.story_context(story_dir)
            return Await(
                self._abs(context),
                result.notes,
                self.write_story,
                epic=epic,
                story_slug=story_slug,
                story_dir=story_dir,
                story_path=story_path,
                mockup=mockup,
                reworks=reworks,
            )
        return Continue(
            result,
            self.check_story,
            epic=epic,
            story_slug=story_slug,
            story_dir=story_dir,
            story_path=story_path,
            mockup=mockup,
            reworks=reworks,
        )

    def check_story(
        self,
        epic: str,
        story_slug: str,
        story_dir: str,
        story_path: str,
        mockup: str = "",
        reworks: int = 0,
    ) -> Continue | Await:
        structure = self.call(validate_story, story_dir)
        if not structure.ok:
            return self._rework_story(
                structure.errors, epic, story_slug, story_dir, story_path, mockup, reworks
            )
        grounding = self.call(
            check_story_grounding,
            story_dir,
            paths.epic_dir(self.ctx.repo_root, epic, self.ctx.epics_dir),
            self.ctx.features_dir,
        )
        if not grounding.ok:
            return self._rework_story(
                grounding.errors, epic, story_slug, story_dir, story_path, mockup, reworks
            )
        return Continue(
            grounding,
            self.audit_story,
            epic=epic,
            story_slug=story_slug,
            story_dir=story_dir,
            story_path=story_path,
            mockup=mockup,
            reworks=reworks,
        )

    def audit_story(
        self,
        epic: str,
        story_slug: str,
        story_dir: str,
        story_path: str,
        mockup: str = "",
        reworks: int = 0,
    ) -> Continue | Await:
        result = self.agent(
            "prompts/audit-story.md",
            returns=AuditResult,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "epic": epic,
                "story_path": story_path,
                "story_slug": story_slug,
                "story_dir": story_dir,
                "features_dir": self.ctx.features_dir,
            },
        )
        if result.status == "failed":
            return self._rework_story(
                result.notes, epic, story_slug, story_dir, story_path, mockup, reworks
            )
        return Continue(result, self.check_add_integrity)

    def _rework_story(
        self,
        notes: str,
        epic: str,
        story_slug: str,
        story_dir: str,
        story_path: str,
        mockup: str,
        reworks: int,
    ) -> Continue | Await:
        if reworks >= MAX_REWORKS:
            context = paths.story_context(story_dir)
            return Await(
                self._abs(context),
                notes,
                self.write_story,
                epic=epic,
                story_slug=story_slug,
                story_dir=story_dir,
                story_path=story_path,
                mockup=mockup,
            )
        ledger = self.call(
            record_attempt, f"{story_dir.rstrip('/')}/attempts.md", str(reworks), notes
        )
        result = self.agent(
            "prompts/rework-story.md",
            returns=WriteStoryResult,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "epic": epic,
                "story_path": story_path,
                "story_slug": story_slug,
                "story_dir": story_dir,
                "features_dir": self.ctx.features_dir,
                "mockup_dir": self.ctx.mockup_dir,
                "mockup_path": mockup,
                "validation_errors": notes,
                "prior_attempts": ledger.prior_attempts,
            },
        )
        return Continue(
            result,
            self.check_story,
            epic=epic,
            story_slug=story_slug,
            story_dir=story_dir,
            story_path=story_path,
            mockup=mockup,
            reworks=reworks + 1,
        )

    def check_add_integrity(self) -> Done:
        report = self.call(verify_integrity)
        if not report.holds and not report.skipped:
            self.call(commit_author, "incomplete", self.epic, self.bullet)
            raise WorkflowFailed(f"story edit broke graph integrity:\n{report.errors}")
        seeded = self.output(seed_story)
        self.call(prune_bullet, self.backlog, seeded.bullet_id, seeded.from_backlog)
        self.call(commit_author, "story", self.epic, self.bullet)
        return Done(report)

    def check_remove_integrity(self, mutation: StoryMutation) -> Done:
        report = self.call(verify_integrity)
        if not report.holds and not report.skipped:
            self.call(commit_author, "incomplete", mutation.epic, mutation.story_slug)
            raise WorkflowFailed(f"story removal broke graph integrity:\n{report.errors}")
        self.call(commit_author, "story", mutation.epic, f"remove {mutation.story_slug}")
        return Done(mutation)
