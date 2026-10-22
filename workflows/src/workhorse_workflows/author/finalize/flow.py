"""Validate and deliver an already-authored milestone without authoring more scope."""
from __future__ import annotations

from pathlib import Path

from workhorse.pyflow import Await, Continue, Done, Workflow, WorkflowFailed
from workhorse_workflows.author.finalize.nodes import (
    mark_milestone_authored,
    validate_artifacts,
    validate_milestone_epics,
    verify_reconcile,
)
from workhorse_workflows.author.shared.nodes import (
    commit_author,
    load_config,
    verify_integrity,
)
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.schemas import OperatorResolution, RunContext

MAX_INTEGRITY_RESOLVES = 2
UNBOUNDED = float("inf")


class Finalize(Workflow):
    """Run the normal epic-mode validation and commit the epics it passed."""

    operator_mode: str = "auto"

    def setup(self) -> RunContext:
        """Resolve repository config for the branch the repo is already on."""
        cfg = self.call(load_config, mode="epic")
        return RunContext(**cfg.model_dump())

    def labels(self) -> dict[str, str]:
        return {
            "work_id": Path(self.ctx.milestone_path).parent.name,
            "progress": "validating and delivering authored milestone",
        }

    def _context(self) -> str:
        return paths.author_context(self.ctx.repo_root)

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
        self.call(commit_author, "incomplete", "", "", self.ctx.milestone_path)
        raise WorkflowFailed(f"{heading}:\n{errors}")

    def start(self) -> Continue:
        if self.operator_mode not in {"auto", "human"}:
            raise WorkflowFailed("finalize operator_mode must be 'auto' or 'human'")
        return Continue(None, self.reconcile)

    def reconcile(self) -> Continue | Await:
        report = self.call(verify_reconcile)
        if report.holds or report.skipped:
            return Continue(report, self.integrity)
        return Await(self._context_path(), report.errors, self.integrity)

    def integrity(self, resolves: int = 0) -> Continue | Await:
        report = self.call(verify_integrity, "")
        if report.holds or report.skipped:
            return Continue(report, self.milestone_epics)
        if self.operator_mode == "human" or resolves >= MAX_INTEGRITY_RESOLVES:
            return Await(self._context_path(), report.errors, self.milestone_epics)
        return Continue(report, self.resolve_graph, notes=report.errors, resolves=resolves)

    def resolve_graph(self, notes: str, resolves: int = 0) -> Continue | Await:
        result = self._resolve_integrity(notes)
        if result.decision == "escalated":
            return Await(self._context_path(), notes, self.milestone_epics)
        return Continue(result, self.integrity, resolves=resolves + 1)

    def milestone_epics(self, resolves: int = 0) -> Continue | Await:
        contract = self.call(validate_milestone_epics, self.ctx.milestone_path)
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
        return Continue(result, self.milestone_epics, resolves=resolves + 1)

    def close(self) -> Done:
        artifacts = self.call(validate_artifacts)
        if not artifacts.ok:
            self._fail_validation("authored artifacts did not validate", artifacts.errors)

        contract = self.call(validate_milestone_epics, self.ctx.milestone_path)
        if not contract.ok:
            self._fail_validation("milestone did not validate", contract.errors)

        self.call(mark_milestone_authored, self.ctx.milestone_path)
        return Done(self.call(commit_author, "epic", "", "", self.ctx.milestone_path))


__all__ = ["Finalize", "MAX_INTEGRITY_RESOLVES"]
