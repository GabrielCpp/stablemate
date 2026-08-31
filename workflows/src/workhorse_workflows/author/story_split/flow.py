"""Standalone split and pre-authoring coverage convergence for one epic."""
from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from workhorse.pyflow import Await, Continue, Done, Workflow, WorkflowFailed
from workhorse_workflows.author.main.nodes import load_config, validate_coverage
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.schemas import (
    Config,
    CoverageReview,
    OperatorResolution,
    StorySplit,
)
from workhorse_workflows.author.story_split.schemas import StorySplitDone
from workhorse_workflows.author.story_split.nodes import record_story_split_review
from workhorse_workflows.kit.telemetry import counter_labels

MAX_REWORKS = 3
MAX_SPLIT_RESOLVES = 2
UNBOUNDED = float("inf")


class StorySplitFlow(Workflow):
    """Create and accept the story graph for one explicitly named epic."""

    epic: str = ""
    backlog: str = ""
    epics_dir: str = ""
    operator_mode: str = "auto"

    BUDGET_LABELS: ClassVar[tuple[str, ...]] = ("cov_reworks", "split_resolves")

    def setup(self) -> Config:
        return self.call(load_config, self.backlog, self.epics_dir, mode="story-split")

    def labels(self) -> dict[str, str]:
        return {"work_id": self.epic, "epic": self.epic, "progress": "splitting stories"}

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        return self.labels() | counter_labels(params, "story_split", self.BUDGET_LABELS)

    def _epic_dir(self) -> str:
        return paths.epic_dir(self.ctx.repo_root, self.epic, self.ctx.epics_dir)

    def _context(self) -> str:
        return paths.epic_context(self._epic_dir())

    def _abs(self, relative: str) -> Path:
        return Path(self.ctx.repo_root) / relative

    def _resolve(self, stage: str, notes: str) -> OperatorResolution:
        return self.agent(
            "shared/prompts/resolve-operator.md",
            returns=OperatorResolution,
            power="high",
            timeout=UNBOUNDED,
            cwd=self.ctx.repo_root,
            args={
                "context_path": self._context(),
                "epic_dir": self._epic_dir(),
                "block_stage": stage,
                "block_notes": notes,
            },
        )

    def start(self) -> Continue:
        if not self.epic.strip():
            raise WorkflowFailed(
                "story-split needs exactly one non-empty 'epic'",
                failure_class="story-split-missing-epic",
            )
        if self.operator_mode not in {"auto", "human"}:
            raise WorkflowFailed(
                "story-split operator_mode must be 'auto' or 'human'",
                failure_class="story-split-invalid-operator-mode",
            )
        return Continue(None, self.split_stories)

    def split_stories(
        self,
        split_resolves: int = 0,
        cov_reworks: int = 0,
        rework_notes: str = "",
    ) -> Continue | Await:
        result = self.agent(
            "story_split/prompts/split-stories.md",
            returns=StorySplit,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "epic": self.epic,
                "epic_dir": self._epic_dir(),
                "rework_notes": rework_notes,
            },
        )
        if result.status == "standoff":
            notes = f"{rework_notes}\n\nStory-split stage declined this rework: {result.notes}"
            return self._gate_coverage(result, notes, split_resolves)
        if result.status != "blocked":
            return Continue(
                result,
                self.check_coverage,
                cov_reworks=cov_reworks,
                split_resolves=split_resolves,
            )
        if self.operator_mode == "human" or split_resolves >= MAX_SPLIT_RESOLVES:
            return Await(
                self._abs(self._context()),
                result.notes,
                self.split_stories,
                split_resolves=split_resolves,
                cov_reworks=cov_reworks,
                rework_notes=rework_notes,
            )
        return Continue(
            result,
            self.resolve_split,
            notes=result.notes,
            split_resolves=split_resolves,
            cov_reworks=cov_reworks,
            rework_notes=rework_notes,
        )

    def resolve_split(
        self,
        notes: str,
        split_resolves: int = 0,
        cov_reworks: int = 0,
        rework_notes: str = "",
    ) -> Await:
        self._resolve("story-split", notes)
        return Await(
            self._abs(self._context()),
            notes,
            self.split_stories,
            split_resolves=split_resolves + 1,
            cov_reworks=cov_reworks,
            rework_notes=rework_notes,
        )

    def check_coverage(
        self, cov_reworks: int = 0, split_resolves: int = 0
    ) -> Continue | Await | Done:
        mechanical = self.call(validate_coverage, self._epic_dir(), require_authored=False)
        if not mechanical.ok:
            return self._rework_coverage(
                mechanical, mechanical.errors, cov_reworks, split_resolves
            )
        review = self.agent(
            "story_split/prompts/review-coverage.md",
            returns=CoverageReview,
            power="high",
            cwd=self.ctx.repo_root,
            args={"epic": self.epic, "epic_dir": self._epic_dir()},
        )
        if review.status == "ok":
            receipt = self.call(record_story_split_review, self.epic)
            return Done(
                StorySplitDone(
                    epic=self.epic,
                    epic_dir=self._epic_dir(),
                    receipt_path=receipt.path,
                    coverage_reworks=cov_reworks,
                    operator_resolutions=split_resolves,
                )
            )
        if review.status == "blocked":
            return self._gate_coverage(review, review.notes, split_resolves)
        return self._rework_coverage(review, review.notes, cov_reworks, split_resolves)

    def _rework_coverage(
        self,
        result: object,
        notes: str,
        cov_reworks: int,
        split_resolves: int,
    ) -> Continue | Await:
        if cov_reworks >= MAX_REWORKS:
            return self._gate_coverage(result, notes, split_resolves)
        return Continue(
            result,
            self.split_stories,
            split_resolves=split_resolves,
            cov_reworks=cov_reworks + 1,
            rework_notes=notes,
        )

    def resolve_coverage(self, notes: str, split_resolves: int = 0) -> Await:
        self._resolve("coverage", notes)
        return Await(
            self._abs(self._context()),
            notes,
            self.split_stories,
            split_resolves=split_resolves + 1,
        )

    def _gate_coverage(
        self, result: object, notes: str, split_resolves: int
    ) -> Continue | Await:
        if self.operator_mode == "human" or split_resolves >= MAX_SPLIT_RESOLVES:
            return Await(
                self._abs(self._context()),
                notes,
                self.split_stories,
                split_resolves=split_resolves,
            )
        return Continue(
            result,
            self.resolve_coverage,
            notes=notes,
            split_resolves=split_resolves,
        )


__all__ = ["StorySplitFlow"]
