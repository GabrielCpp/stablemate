"""Story-level edit entry point; epic-edit owns the resulting reconciliation."""
from __future__ import annotations

from workhorse.pyflow import Done, Workflow
from workhorse_workflows.author.epic_edit import EpicEdit
from workhorse_workflows.author.nodes import adopt_backlog, load_config
from workhorse_workflows.author.shared.schemas import Config
from workhorse_workflows.author.story_edit.nodes import resolve_story_intent


class StoryEdit(Workflow):
    """Translate one story add/remove command into an epic-edit handoff."""

    action: str = "add"
    epic: str = ""
    bullet: str = ""
    story: str = ""
    reason: str = ""
    force: bool = False
    backlog: str = ""
    epics_dir: str = ""
    operator_mode: str = "auto"

    def setup(self) -> Config:
        return self.call(load_config, self.backlog, self.epics_dir)

    def labels(self) -> dict[str, str]:
        work_id = self.story if self.action == "remove" else self.epic
        return {"work_id": work_id, "epic": self.epic, "progress": "reconciling epic scope"}

    def start(self) -> Done:
        if self.action == "add":
            self.call(adopt_backlog, self.ctx.backlog_path)
        intent = self.call(
            resolve_story_intent,
            self.action,
            self.epic,
            self.story,
            self.bullet,
            self.reason,
            self.force,
            self.ctx.backlog_path,
            self.ctx.epics_dir,
        )
        result = self.handoff(
            EpicEdit,
            intent=intent,
            backlog=self.backlog,
            epics_dir=self.epics_dir,
            operator_mode=self.operator_mode,
            branch_run_dir=str(self.run_dir),
        )
        return Done(result)


__all__ = ["StoryEdit"]
