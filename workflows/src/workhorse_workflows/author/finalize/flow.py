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
from workhorse_workflows.author.shared.schemas import Defects, OperatorResolution, RunContext

MAX_INTEGRITY_RESOLVES = 2
CHECKS = ("reconcile", "integrity", "milestone")
RESOLVABLE = frozenset({"integrity", "milestone"})
UNBOUNDED = float("inf")


class Finalize(Workflow):
    """Run the normal epic-mode validation and commit the epics it passed."""

    operator_mode: str = "auto"
    baseline: str = ""

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
        return Continue(None, self.verify).because("operator mode is auto or human")

    def _run(self, check: str) -> Defects:
        if check == "reconcile":
            report = self.call(verify_reconcile, self.baseline)
        elif check == "integrity":
            report = self.call(verify_integrity, "")
        else:
            return self.call(validate_milestone_epics, self.ctx.milestone_path)
        return Defects(ok=report.holds or report.skipped, errors=report.errors)

    def verify(self, check: int = 0, resolves: int = 0) -> Continue | Await:
        """Run the closing checks in order, repair a failed one, or park it for the operator."""
        if check == len(CHECKS):
            return Continue(None, self.close).because("every closing check ran")
        name = CHECKS[check]
        report = self._run(name)
        if report.ok:
            return Continue(report, self.verify, check=check + 1).because("the check holds")
        if name in RESOLVABLE and self.operator_mode == "auto" and resolves < MAX_INTEGRITY_RESOLVES:
            return Continue(report, self.resolve, check=check, notes=report.errors, resolves=resolves).because(
                "an agent may repair it"
            )
        return Await(self._context_path(), report.errors, self.verify, check=check + 1).because(
            "parked for the operator"
        )

    def resolve(self, check: int, notes: str, resolves: int = 0) -> Continue | Await:
        """Let an agent repair what a closing check found, then run that check again."""
        result = self._resolve_integrity(notes)
        if result.decision == "escalated":
            return Await(self._context_path(), notes, self.verify, check=check + 1).because(
                "the agent escalated"
            )
        return Continue(result, self.verify, check=check, resolves=resolves + 1).because("repaired")

    def close(self) -> Done:
        artifacts = self.call(validate_artifacts)
        if not artifacts.ok:
            self._fail_validation("authored artifacts did not validate", artifacts.errors)

        contract = self.call(validate_milestone_epics, self.ctx.milestone_path)
        if not contract.ok:
            self._fail_validation("milestone did not validate", contract.errors)

        self.call(mark_milestone_authored, self.ctx.milestone_path)
        return Done(self.call(commit_author, "epic", "", "", self.ctx.milestone_path)).because(
            "the milestone is authored"
        )


__all__ = ["Finalize", "MAX_INTEGRITY_RESOLVES"]
