"""Build or reuse exactly one milestone for an approved roadmap."""
from __future__ import annotations

from pathlib import Path

from workhorse.pyflow import Await, Done, Workflow
from workhorse_workflows.author.milestone.nodes import prepare_milestone, validate_milestone
from workhorse_workflows.author.milestone.schemas import (
    MilestoneContext,
    MilestoneResult,
    MilestoneValidation,
)
from workhorse_workflows.author.shared import paths


class Milestone(Workflow):
    """The milestone-only boundary; no epic, git, or downstream work is reachable."""

    roadmap: str = ""
    epics_dir: str = ""

    def setup(self) -> MilestoneContext:
        return self.call(prepare_milestone, self.roadmap, self.epics_dir)

    def labels(self) -> dict[str, str]:
        return {"work_id": Path(self.roadmap).stem}

    def start(self) -> Done | Await:
        result = self.agent(
            "milestone/prompts/build-milestone.md",
            returns=MilestoneResult,
            power="high",
            cwd=self.ctx.repo_root,
            args={"roadmap": self.ctx.roadmap},
        )
        context_path = Path(self.ctx.repo_root) / paths.author_context(
            self.ctx.repo_root, self.ctx.epics_dir
        )
        if result.status == "blocked":
            return Await(context_path, result.notes, self.start)
        validation = self.call(validate_milestone, self.ctx)
        if not validation.ok:
            return Await(context_path, validation.errors, self.start)
        return Done(validation)


__all__ = ["Milestone", "MilestoneValidation"]
