"""Typed contracts for slicing one plan into independently implemented phases.

The source plan stays an immutable prose artifact. The slicing turn proposes phase
boundaries and the self-contained document each phase needs; deterministic nodes then
prove the slicing covers the source before any phase is handed to `implement-plan`.
"""
from __future__ import annotations

from pydantic import Field

from workhorse_workflows.coder.implement_plan.schemas import VerificationCommand
from workhorse_workflows.coder.shared.schemas._base import CoderResult


class PlanSlice(CoderResult):
    """One phase of the source plan, as the slicing turn proposed it."""

    id: str = ""
    title: str = ""
    covers: list[str] = Field(default_factory=list)
    body: str = ""


class PlanSlicing(CoderResult):
    """The slicing-only turn's complete answer."""

    status: str = ""
    summary: str = ""
    phase_headings: list[str] = Field(default_factory=list)
    slices: list[PlanSlice] = Field(default_factory=list)
    final_verification: list[VerificationCommand] = Field(default_factory=list)


class StagedSlice(CoderResult):
    """A validated slice written to disk; the digest is what the phase implements."""

    id: str = ""
    title: str = ""
    covers: list[str] = Field(default_factory=list)
    path: str = ""
    digest: str = ""


class PreparedSlices(CoderResult):
    """Validated staging authority carried in every subsequent checkpoint.

    Slice prose lives in the run directory rather than in this model: a checkpoint the
    operator has to read at hour 30 must stay small, and the digest is what pins the
    document the phase actually implemented.
    """

    slices: list[StagedSlice] = Field(default_factory=list)
    final_verification: list[VerificationCommand] = Field(default_factory=list)
    summary: str = ""


class StagePlanContext(CoderResult):
    """Immutable setup facts restored from the checkpoint on resume."""

    repo_root: str = ""
    source_path: str = ""
    plan_text: str = ""
    plan_digest: str = ""
    stage_dir: str = ""
    branch: str = ""
    base_commit: str = ""


class StageOutcome(CoderResult):
    """What one finished phase contributed, taken from its own `Done(...)` value."""

    id: str = ""
    slice_digest: str = ""
    plan_digest: str = ""
    task_count: int = 0
    review_issue_count: int = 0
    review_passes: int = 0
    final_commit: str = ""


class StagedPlanResult(CoderResult):
    """The terminal value of a staged plan run."""

    status: str = ""
    plan_digest: str = ""
    stage_count: int = 0
    task_count: int = 0
    review_issue_count: int = 0
    final_commit: str = ""


__all__ = [
    "PlanSlice",
    "PlanSlicing",
    "PreparedSlices",
    "StageOutcome",
    "StagePlanContext",
    "StagedPlanResult",
    "StagedSlice",
]
