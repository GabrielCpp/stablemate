"""Standalone story-split and PM review convergence for one epic."""
from __future__ import annotations

from workhorse.pyflow import Done, Workflow, WorkflowFailed, dry_run
from workhorse_workflows.author.draft import DraftLoop
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.nodes import load_config
from workhorse_workflows.author.shared.schemas import Config
from workhorse_workflows.author.story_split.schemas import StorySplitDone


@dry_run(epic="dry-run")
class StorySplitFlow(Workflow):
    """Create and accept the story graph for one explicitly named epic."""

    epic: str = ""
    note: str = ""

    def setup(self) -> Config:
        return self.call(load_config, mode="story-split")

    def labels(self) -> dict[str, str]:
        return {"work_id": self.epic, "epic": self.epic, "progress": "splitting stories"}

    def _epic_dir(self) -> str:
        return paths.epic_dir(self.ctx.repo_root, self.epic)

    def start(self) -> Done:
        """Draft the epic's story graph until the PM passes it."""
        if not self.epic.strip():
            raise WorkflowFailed(
                "story-split needs exactly one non-empty 'epic'",
                failure_class="story-split-missing-epic",
            )
        done = self.handoff(
            DraftLoop,
            kind="story-split",
            subject=self._epic_dir(),
            epic=self.epic,
            epic_dir=self._epic_dir(),
            args={"epic": self.epic, "epic_dir": self._epic_dir(), "ledger": self.ctx.pm_ledger},
            note=self.note,
        )
        status = "blocked" if done.status == "blocked" else "accepted"
        if status == "blocked":
            self.logger.warning("the story split of %s stays blocked: %s", self.epic, done.notes)
        return Done(
            StorySplitDone(
                status=status,
                epic=self.epic,
                epic_dir=self._epic_dir(),
                notes=done.notes,
                reworks=done.reworks,
                answers=done.answers,
            )
        ).because("the split passed or stayed blocked")


__all__ = ["StorySplitFlow"]
