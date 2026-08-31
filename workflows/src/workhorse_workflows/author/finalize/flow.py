"""Validate and deliver an already-authored roadmap without authoring more scope."""
from __future__ import annotations

from pathlib import Path

from workhorse.pyflow import Await, Continue, Done, Workflow, WorkflowFailed
from workhorse_workflows.author.main.nodes import (
    commit_author,
    load_config,
    mark_roadmap_authored,
    open_author_pr,
    validate_artifacts,
    validate_roadmap_milestone,
    verify_integrity,
    verify_reconcile,
)
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.schemas import OperatorResolution, RunContext

MAX_RECONCILE_RESOLVES = 2
MAX_INTEGRITY_RESOLVES = 2
UNBOUNDED = float("inf")


class Finalize(Workflow):
    """Run the normal epic-mode validation, commit, and PR tail directly."""

    roadmap: str = ""
    epics_dir: str = ""
    base_branch: str = "main"
    author_branch: str = ""
    operator_mode: str = "auto"

    def setup(self) -> RunContext:
        """Resolve repository config while preserving the caller-owned branch."""
        cfg = self.call(load_config, "", self.epics_dir, roadmap=self.roadmap, mode="epic")
        return RunContext(
            **cfg.model_dump(),
            base_branch=self.base_branch,
            author_branch=self.author_branch,
        )

    def labels(self) -> dict[str, str]:
        return {
            "work_id": Path(self.roadmap).stem,
            "progress": "validating and delivering authored roadmap",
        }

    def _context(self) -> str:
        return paths.author_context(self.ctx.repo_root, self.ctx.epics_dir)

    def _context_path(self) -> Path:
        return Path(self.ctx.repo_root) / self._context()

    def _resolve_integrity(self, notes: str) -> OperatorResolution:
        return self.agent(
            "finalize/prompts/resolve-integrity.md",
            returns=OperatorResolution,
            power="high",
            timeout=UNBOUNDED,
            cwd=self.ctx.repo_root,
            args={
                "context_path": self._context(),
                "epics_dir": self.ctx.epics_dir,
                "integrity_errors": notes,
            },
        )

    def _fail_validation(self, heading: str, errors: str) -> None:
        self.call(commit_author, "incomplete", "", "", self.ctx.roadmap_path)
        raise WorkflowFailed(f"{heading}:\n{errors}")

    def start(self) -> Continue:
        if self.operator_mode not in {"auto", "human"}:
            raise WorkflowFailed("finalize operator_mode must be 'auto' or 'human'")
        return Continue(None, self.reconcile)

    def reconcile(self, resolves: int = 0) -> Continue | Await:
        report = self.call(verify_reconcile, self.ctx.epics_dir)
        if report.holds or report.skipped:
            return Continue(report, self.integrity)
        if self.operator_mode == "human" or resolves >= MAX_RECONCILE_RESOLVES:
            return Await(self._context_path(), report.errors, self.integrity)
        return Continue(report, self.resolve_reconcile, notes=report.errors, resolves=resolves)

    def resolve_reconcile(self, notes: str, resolves: int = 0) -> Await:
        self.agent(
            "shared/prompts/resolve-operator.md",
            returns=OperatorResolution,
            power="high",
            timeout=UNBOUNDED,
            cwd=self.ctx.repo_root,
            args={
                "context_path": self._context(),
                "epic_dir": self.ctx.epics_dir,
                "block_stage": "reconciliation",
                "block_notes": notes,
            },
        )
        return Await(self._context_path(), notes, self.integrity)

    def integrity(self, resolves: int = 0) -> Continue | Await:
        report = self.call(verify_integrity, "", self.ctx.epics_dir)
        if report.holds or report.skipped:
            return Continue(report, self.roadmap_milestone)
        if self.operator_mode == "human" or resolves >= MAX_INTEGRITY_RESOLVES:
            return Await(self._context_path(), report.errors, self.roadmap_milestone)
        return Continue(report, self.resolve_graph, notes=report.errors, resolves=resolves)

    def resolve_graph(self, notes: str, resolves: int = 0) -> Continue | Await:
        result = self._resolve_integrity(notes)
        if result.decision == "escalated":
            return Await(self._context_path(), notes, self.roadmap_milestone)
        return Continue(result, self.integrity, resolves=resolves + 1)

    def roadmap_milestone(self, resolves: int = 0) -> Continue | Await:
        contract = self.call(validate_roadmap_milestone, self.ctx.roadmap_path)
        if contract.ok:
            return Continue(contract, self.close)
        if self.operator_mode == "human" or resolves >= MAX_INTEGRITY_RESOLVES:
            return Await(self._context_path(), contract.errors, self.close)
        return Continue(
            contract,
            self.resolve_milestone,
            notes=contract.errors,
            resolves=resolves,
        )

    def resolve_milestone(self, notes: str, resolves: int = 0) -> Continue | Await:
        result = self._resolve_integrity(notes)
        if result.decision == "escalated":
            return Await(self._context_path(), notes, self.close)
        return Continue(result, self.roadmap_milestone, resolves=resolves + 1)

    def close(self) -> Done:
        artifacts = self.call(validate_artifacts)
        if not artifacts.ok:
            self._fail_validation("authored artifacts did not validate", artifacts.errors)

        contract = self.call(validate_roadmap_milestone, self.ctx.roadmap_path)
        if not contract.ok:
            self._fail_validation("roadmap milestone did not validate", contract.errors)

        self.call(mark_roadmap_authored, self.ctx.roadmap_path)
        self.call(commit_author, "epic", "", "", self.ctx.roadmap_path)
        return Done(
            self.call(
                open_author_pr,
                self.ctx.base_branch,
                self.ctx.author_branch,
                "epic",
                "",
                "",
                self.ctx.roadmap_path,
            )
        )


__all__ = ["Finalize", "MAX_INTEGRITY_RESOLVES", "MAX_RECONCILE_RESOLVES"]
