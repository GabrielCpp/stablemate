"""Flat Author composition: select one artifact-derived stage and hand it off."""
from __future__ import annotations

from collections.abc import Sequence

from workhorse.pyflow import Continue, Done, Workflow
from workhorse_workflows.author.epic_author import EpicAuthor
from workhorse_workflows.author.epic_split import EpicSplit
from workhorse_workflows.author.finalize import Finalize
from workhorse_workflows.author.main.nodes import (
    adopt_backlog,
    branch_author,
    load_config,
    plan_author_step,
    prune_bullet,
    seed_story,
)
from workhorse_workflows.author.milestone import Milestone
from workhorse_workflows.author.parity_surveyor import ParitySurveyor
from workhorse_workflows.author.shared.schemas import RunContext
from workhorse_workflows.author.story_author import StoryAuthor
from workhorse_workflows.author.story_split import StorySplitFlow
from workhorse_workflows.author.surveyor import Surveyor


class Author(Workflow):
    """Compose independently runnable author stages over one roadmap."""

    mode: str = "epic"
    epic: str = ""
    bullet: str = ""
    layers: str = ""
    services: str = ""
    rubric: str = "docs/survey/rubric.md"
    survey_dir: str = "docs/survey"
    baseline_inventory: str = ""
    parity_survey_dir: str = "docs/survey/legacy-vs-new"
    operator_mode: str = "auto"

    def setup(self) -> RunContext:
        """Resolve paths and create the one branch shared by every handed-off stage."""
        cfg = self.call(load_config, mode=self.mode)
        branches = self.call(branch_author, str(self.run_dir), self.mode)
        return RunContext(
            **cfg.model_dump(),
            base_branch=branches.base_branch,
            author_branch=branches.author_branch,
        )

    def start(self) -> Continue | Done:
        """Dispatch discovery modes, one backlog story, or the flat roadmap planner."""
        if self.mode == "survey":
            return Done(self.handoff(
                Surveyor,
                rubric=self.rubric,
                survey_dir=self.survey_dir,
                operator_mode=self.operator_mode,
            ))
        if self.mode == "parity-survey":
            return Done(self.handoff(
                ParitySurveyor,
                baseline_inventory=self.baseline_inventory,
                survey_dir=self.parity_survey_dir,
            ))
        if self.mode == "story":
            self.call(adopt_backlog)
            seeded = self.call(
                seed_story,
                self.epic,
                self.bullet,
                layers=self.layers,
                services=self.services,
            )
            self.handoff(
                StoryAuthor,
                epic=self.epic,
                story=seeded.story_slug,
                feedback_dir=str(self.run_dir),
                operator_mode=self.operator_mode,
            )
            return Done(self.call(
                prune_bullet,
                seeded.bullet_id,
                seeded.from_backlog,
            ))
        return Continue(None, self.next_stage)

    def next_stage(self, blocked: Sequence[str] = ()) -> Continue | Done:
        """Run exactly one artifact-derived stage, then plan again from disk."""
        step = self.call(plan_author_step, blocked=tuple(blocked))
        if step.kind == "milestone":
            result = self.handoff(Milestone)
        elif step.kind == "epic-split":
            result = self.handoff(EpicSplit, operator_mode=self.operator_mode)
        elif step.kind == "epic-author":
            result = self.handoff(
                EpicAuthor,
                epic=step.epic,
                operator_mode=self.operator_mode,
            )
        elif step.kind == "story-split":
            result = self.handoff(
                StorySplitFlow,
                epic=step.epic,
                operator_mode=self.operator_mode,
            )
        elif step.kind == "story-author":
            result = self.handoff(
                StoryAuthor,
                epic=step.epic,
                story=step.story,
                feedback_dir=str(self.run_dir),
                operator_mode=self.operator_mode,
            )
            if result.status == "blocked":
                self.logger.warning(
                    "story '%s' in epic '%s' remains audit-blocked; continuing the flat queue",
                    step.story,
                    step.epic,
                )
                return Continue(
                    result,
                    self.next_stage,
                    blocked=[*blocked, f"{step.epic}/{step.story}"],
                )
        else:
            return Done(self.handoff(
                Finalize,
                base_branch=self.ctx.base_branch,
                author_branch=self.ctx.author_branch,
                operator_mode=self.operator_mode,
            ))
        return Continue(result, self.next_stage, blocked=list(blocked))


__all__ = ["Author"]
