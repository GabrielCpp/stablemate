"""Directly author one explicit epic without selecting or entering downstream stages."""
from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from workhorse.pyflow import Await, Continue, Done, Workflow
from workhorse_workflows.author.epic_author.nodes import prepare_epic_target, validate_authored_epic
from workhorse_workflows.author.epic_author.schemas import EpicAuthorContext, EpicAuthorDone
from workhorse_workflows.author.main.nodes import load_config
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.schemas import OperatorResolution, WriteEpicResult
from workhorse_workflows.kit.telemetry import counter_labels

MAX_RESOLVES = 2
UNBOUNDED = float("inf")


class EpicAuthor(Workflow):
    """Run the current epic-prose and seed pass for one caller-selected epic."""

    epic: str = ""
    operator_mode: str = "auto"

    BUDGET_LABELS: ClassVar[tuple[str, ...]] = ("resolves",)

    def setup(self) -> EpicAuthorContext:
        """Resolve config and the explicit target only; never create a branch."""
        cfg = self.call(load_config, mode="epic")
        target = self.call(prepare_epic_target, self.epic)
        return EpicAuthorContext(**cfg.model_dump(), **target.model_dump())

    def labels(self) -> dict[str, str]:
        return {"work_id": self.epic, "epic": self.epic, "progress": "authoring one epic"}

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        return self.labels() | counter_labels(params, "epic_author", self.BUDGET_LABELS)

    def _context_path(self) -> Path:
        return Path(self.ctx.repo_root) / paths.epic_context(self.ctx.epic_dir)

    def _gate(self, result: object, notes: str, resolves: int) -> Continue | Await:
        if self.operator_mode == "human" or resolves >= MAX_RESOLVES:
            return Await(self._context_path(), notes, self.author_epic, resolves=resolves)
        return Continue(result, self.resolve_epic, notes=notes, resolves=resolves)

    def start(self) -> Continue:
        return Continue(None, self.author_epic)

    def author_epic(self, resolves: int = 0) -> Continue | Await | Done:
        self.logger.info("authoring epic %s", self.ctx.epic, extra={"activity": True})
        result = self.agent(
            "epic_author/prompts/write-epic.md",
            returns=WriteEpicResult,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "epic": self.ctx.epic,
                "epic_dir": self.ctx.epic_dir,
                "roadmap": self.ctx.roadmap_path,
                "features_dir": self.ctx.features_dir,
            },
        )
        if result.status == "blocked":
            return self._gate(result, result.notes, resolves)
        evidence = self.call(validate_authored_epic, self.ctx.epic)
        if not evidence.ok:
            return self._gate(evidence, evidence.errors, resolves)
        return Done(
            EpicAuthorDone(
                epic=evidence.epic,
                epic_dir=evidence.epic_dir,
                epic_path=evidence.epic_path,
                seed_count=evidence.seed_count,
                operator_resolutions=resolves,
            )
        )

    def resolve_epic(self, notes: str, resolves: int = 0) -> Await:
        """Diagnose locally with the main resolver, then resume the same epic."""
        self.agent(
            "shared/prompts/resolve-operator.md",
            returns=OperatorResolution,
            power="high",
            timeout=UNBOUNDED,
            cwd=self.ctx.repo_root,
            args={
                "context_path": paths.epic_context(self.ctx.epic_dir),
                "epic_dir": self.ctx.epic_dir,
                "block_stage": "write-epic",
                "block_notes": notes,
            },
        )
        return Await(
            self._context_path(),
            notes,
            self.author_epic,
            resolves=resolves + 1,
        )


__all__ = ["EpicAuthor", "MAX_RESOLVES"]
