"""Typed contracts for the plan-to-commits Coder flow.

The plan itself is prose and remains an input artifact.  The decomposition turn turns it
into these deliberately small packets; deterministic nodes then validate and persist the
packets before any implementation turn is allowed to edit the checkout.
"""
from __future__ import annotations

from pydantic import Field

from workhorse_workflows.coder.shared.schemas._base import CoderResult


class VerificationCommand(CoderResult):
    """One portable command: argv, not shell source, plus a repo-relative cwd."""

    argv: list[str] = Field(default_factory=list)
    cwd: str = "."
    timeout_s: int = 1800


class PlanTask(CoderResult):
    """One dependency-ordered, commit-sized implementation concern."""

    id: str = ""
    title: str = ""
    objective: str = ""
    acceptance: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    paths: list[str] = Field(default_factory=list)
    verification: list[VerificationCommand] = Field(default_factory=list)
    commit_type: str = ""
    commit_scope: str = ""


class PlanDecomposition(CoderResult):
    """The planning-only turn's complete answer."""

    status: str = ""
    summary: str = ""
    tasks: list[PlanTask] = Field(default_factory=list)
    final_verification: list[VerificationCommand] = Field(default_factory=list)


class PlanRunContext(CoderResult):
    """Immutable setup facts restored from the checkpoint on resume."""

    repo_root: str = ""
    source_path: str = ""
    plan_text: str = ""
    plan_digest: str = ""
    worklist_path: str = ""
    branch: str = ""
    base_commit: str = ""
    origin_digest: str = ""
    git_control_digest: str = ""
    other_refs_digest: str = ""
    run_nonce: str = ""


class PreparedPlan(CoderResult):
    """Validated execution authority carried in every subsequent checkpoint."""

    tasks: list[PlanTask] = Field(default_factory=list)
    final_verification: list[VerificationCommand] = Field(default_factory=list)
    summary: str = ""


class ImplementationResult(CoderResult):
    """An implementation/repair turn's report; deterministic checks remain authoritative."""

    status: str = ""
    notes: str = ""


class TaskDecision(CoderResult):
    phase: str = ""
    commit_sha: str = ""


class VerificationResult(CoderResult):
    passed: bool = False
    findings: str = ""


class CommitResult(CoderResult):
    committed: bool = False
    commit_sha: str = ""


class PublishResult(CoderResult):
    pushed: bool = False
    commit_sha: str = ""


class PlanImplementationResult(CoderResult):
    status: str = ""
    plan_digest: str = ""
    task_count: int = 0
    final_commit: str = ""


__all__ = [
    "CommitResult",
    "ImplementationResult",
    "PlanDecomposition",
    "PlanImplementationResult",
    "PlanRunContext",
    "PlanTask",
    "PreparedPlan",
    "PublishResult",
    "TaskDecision",
    "VerificationCommand",
    "VerificationResult",
]