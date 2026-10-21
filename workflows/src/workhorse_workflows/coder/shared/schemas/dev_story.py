"""The dev lane's models: the dev owner's readiness claim, its review's findings, and their settlement."""
from __future__ import annotations

from typing import Literal

from pydantic import Field
from workhorse.pyflow import dry_run

from workhorse_workflows.coder.shared.schemas._base import CoderResult
from workhorse_workflows.coder.shared.schemas.dev import PlanFields
from workhorse_workflows.coder.shared.schemas.review import ReviewFinding


class FollowUp(CoderResult):
    """Undone product work on this story's feature that the working slice does not need, filed rather than done on the side."""

    title: str = Field(description="What the work is, in one line a person can act on.")
    reason: str = Field(
        description="Why the slice works without it, and what it would improve."
    )


@dry_run(status="ready")
class DevResult(PlanFields):
    """`dev/prompts/dev-story.md` — the dev owner's readiness claim for its story."""

    status: Literal["ready", "blocked"] = Field(
        description="`ready` when the story is built, its plan files are written, and every "
        "gate the plan declares ran green in your last pass. `blocked` when something only "
        "the operator can decide stops you, and you have tried every route the repository "
        "itself offers.",
    )
    notes: str = Field(
        default="",
        description="What you built and the commands you ran green. On `blocked`, the one "
        "question that would unblock you and what you ruled out before asking it.",
    )
    follow_ups: list[FollowUp] = Field(
        default=[],
        description="Product work on this story's feature that the working slice does not "
        "need and nobody has done yet, one entry each. A failure is never one: fix it on the "
        "story branch. These are never one either: a finding resolved during this run, a "
        "defect or warning that predates this story and that its change did not cause, a "
        "remark about docs or a story or plan file's status, and a remark about the toolchain "
        "such as commit trailers, ostler or packet attribution. Each is a run finding for "
        "the operator, so put it in `notes`. The run files each entry right after this story "
        "and works it through dev, QA and docs. "
        "Leave it empty when you are working a follow-up yourself: a follow-up files none "
        "of its own.",
    )
    findings: list[ReviewFinding] = Field(
        default=[],
        description="Every finding your reviewer reported this turn, verbatim and in its "
        "order, before triage drops any. The run files the nth one under the review prefix "
        "plus n, and the answer file answers it under that id. Empty on a turn that ran no "
        "review.",
    )


class DevOutcome(CoderResult):
    """What the dev owner flow hands back to the run."""

    status: Literal["ready", "replan"] = "ready"
    operator_notes: str = ""
    settled: list[str] = []
    declined: list[str] = []


class Settlement(CoderResult):
    """One sign-off pass: which finding items held, which were declined, which stay open."""

    settled: list[str] = []
    declined: list[str] = []
    open: list[str] = []
    rejected: dict[str, str] = {}
    errors: list[str] = []


__all__ = [
    "FollowUp",
    "DevOutcome",
    "DevResult",
    "Settlement",
]
