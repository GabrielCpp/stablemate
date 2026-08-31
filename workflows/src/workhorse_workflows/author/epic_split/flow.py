"""Split one roadmap milestone into an ordered list of epic skeletons."""
from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from workhorse.pyflow import Await, Continue, Done, Workflow
from workhorse_workflows.author.epic_split.nodes import prepare_epic_split, validate_epic_split
from workhorse_workflows.author.epic_split.schemas import (
    EpicSplitContext,
    EpicSplitResult,
    EpicSplitReview,
    OperatorResolution,
)
from workhorse_workflows.author.shared import paths
from workhorse_workflows.kit.telemetry import counter_labels

MAX_REWORKS = 3
MAX_RESOLVES = 2
UNBOUNDED = float("inf")


class EpicSplit(Workflow):
    """The epic-skeleton boundary; epic prose, seeds, stories, and delivery are unreachable."""

    operator_mode: str = "auto"

    BUDGET_LABELS: ClassVar[tuple[str, ...]] = ("reworks", "resolves")

    def setup(self) -> EpicSplitContext:
        return self.call(prepare_epic_split)

    def labels(self) -> dict[str, str]:
        return {"work_id": Path(self.ctx.roadmap).stem}

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        return self.labels() | counter_labels(params, "epic_split", self.BUDGET_LABELS)

    def _context_path(self) -> Path:
        return Path(self.ctx.repo_root) / paths.author_context(self.ctx.repo_root)

    def _split_args(self, review_notes: str = "") -> dict[str, str]:
        return {
            "roadmap": self.ctx.roadmap,
            "milestone": self.ctx.milestone_path,
            "epics_dir": self.ctx.epics_dir,
            "review_notes": review_notes,
        }

    def start(self, resolves: int = 0) -> Continue:
        result = self.agent(
            "epic_split/prompts/split-epics.md",
            returns=EpicSplitResult,
            power="high",
            cwd=self.ctx.repo_root,
            args=self._split_args(),
        )
        return Continue(result, self.review, resolves=resolves)

    def review(self, reworks: int = 0, resolves: int = 0) -> Continue | Await | Done:
        result = self.agent(
            "epic_split/prompts/review-epic-split.md",
            returns=EpicSplitReview,
            power="high",
            cwd=self.ctx.repo_root,
            args=self._split_args(),
        )
        notes = result.notes
        if result.status == "approved":
            validation = self.call(validate_epic_split, self.ctx)
            if validation.ok:
                return Done(validation)
            notes = validation.errors
        if result.status != "blocked" and reworks < MAX_REWORKS:
            return Continue(result, self.rework, notes=notes, reworks=reworks, resolves=resolves)
        if self.operator_mode == "human" or resolves >= MAX_RESOLVES:
            return Await(self._context_path(), notes, self.start, resolves=resolves)
        return Continue(result, self.resolve, notes=notes, resolves=resolves)

    def rework(self, notes: str, reworks: int = 0, resolves: int = 0) -> Continue:
        result = self.agent(
            "epic_split/prompts/rework-epic-split.md",
            returns=EpicSplitResult,
            power="high",
            cwd=self.ctx.repo_root,
            args=self._split_args(notes),
        )
        return Continue(result, self.review, reworks=reworks + 1, resolves=resolves)

    def resolve(self, notes: str, resolves: int = 0) -> Await:
        self.agent(
            "epic_split/prompts/resolve-epic-split.md",
            returns=OperatorResolution,
            power="high",
            timeout=UNBOUNDED,
            cwd=self.ctx.repo_root,
            args={
                **self._split_args(),
                "context_path": str(self._context_path()),
                "block_notes": notes,
            },
        )
        return Await(self._context_path(), notes, self.start, resolves=resolves + 1)


__all__ = ["EpicSplit", "MAX_REWORKS", "MAX_RESOLVES"]
