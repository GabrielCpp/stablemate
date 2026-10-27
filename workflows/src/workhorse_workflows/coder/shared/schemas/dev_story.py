"""The dev lane's models: the dev owner's readiness claim, its review's findings, and their settlement."""
from __future__ import annotations

from typing import Literal

from pydantic import Field
from workhorse.pyflow import dry_run

from workhorse_workflows.coder.shared.schemas._base import CoderResult
from workhorse_workflows.coder.shared.schemas.dev import PlanFields
from workhorse_workflows.coder.shared.schemas.review import ReviewFinding


class FollowUp(CoderResult):
    """Undone product work on this story's feature that the working slice does not need, filed as a record on the debt register rather than done on the side."""

    title: str = Field(description="What the work is, in one line a person can act on.")
    reason: str = Field(
        description="Why the slice works without it, and what it would improve."
    )
    repo: str = Field(
        default="",
        description="The repository of the workspace the work sits in, by the name the "
        "workspace gives it. Leave it empty only when the run has one repository.",
    )
    area: str = Field(
        description="The module or service area the work sits in, as one lowercase kebab "
        "word such as `billing` or `auth`.",
    )
    pattern: str = Field(
        description="The kind of fix the work calls for, as a short lowercase kebab phrase "
        "such as `extract-module` or `widen-api`.",
    )
    symbols: list[str] = Field(
        default=[],
        description="The files or symbols the work touches.",
    )


class Departure(CoderResult):
    """One change the build made to the plan, and the advice it rests on."""

    change: str = Field(
        description="What the build does differently from the plan, and where `plan.md` now records it."
    )
    reason: str = Field(
        description="Why building the plan as written would fail a criterion or a gate."
    )
    advice: str = Field(
        default="",
        description="The advisor's answer, copied as given, and why you did not follow it if you "
        "did not. Empty only when no advisor is offered.",
    )


class Consult(CoderResult):
    """One question the review put to the advisor before declining a finding."""

    finding: str = Field(description="The id of the finding, as the answer file heads it.")
    question: str = Field(description="The question you asked, in one line.")
    advice: str = Field(
        description="The advisor's answer, copied as given, and why you did not follow it if you did not."
    )


@dry_run(status="ready")
class PlanResult(CoderResult):
    """`dev/prompts/dev-plan.md`: the plan phase's claim that the plan files are written."""

    status: Literal["ready", "blocked"] = Field(
        description="`ready` when `plan.md` and its service files are written and committed. "
        "`blocked` when something only the operator can decide stops you, and you have tried "
        "every route the repository itself offers.",
    )
    notes: str = Field(
        default="",
        description="What the plan decided and where it is recorded. On `blocked`, the one "
        "question that would unblock you and what you ruled out before asking it.",
    )


@dry_run(status="ready")
class BuildResult(CoderResult):
    """`dev/prompts/dev-build.md`: the build phase's claim that the plan is built."""

    status: Literal["ready", "blocked"] = Field(
        description="`ready` when every planned change is built and committed, every gate the "
        "plan declares ran green in your last pass, and the Acceptance Walk has an entry per "
        "criterion. `blocked` when something only the operator can decide stops you, and you "
        "have tried every route the repository itself offers.",
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
        "the operator, so put it in `notes`. The run files each entry as a record on the debt "
        "register, where no lane works it. Give each entry the repository, area and pattern it sits in. "
        "Leave it empty when you are working a follow-up yourself: a follow-up files none "
        "of its own.",
    )
    departures: list[Departure] = Field(
        default=[],
        description="Every change the build made to the plan, one entry each. Empty when the "
        "build followed the plan as written.",
    )


@dry_run(status="ready")
class DevResult(PlanFields):
    """`dev/prompts/dev-review.md`: the review phase's claim that the story is reviewed and every finding answered."""

    status: Literal["ready", "blocked"] = Field(
        description="`ready` when the story is reviewed, every finding is answered, and every "
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
        "the operator, so put it in `notes`. The run files each entry as a record on the debt "
        "register, where no lane works it. Give each entry the repository, area and pattern it sits in. "
        "Leave it empty when you are working a follow-up yourself: a follow-up files none "
        "of its own.",
    )
    findings: list[ReviewFinding] = Field(
        default=[],
        description="Every finding your reviewer reported this turn, verbatim and in its "
        "order, before triage drops any. The run files the nth one under the review prefix "
        "plus n, and the answer file answers it under that id. A finding filed before this "
        "turn is answered in the answer file and never listed here. Empty on a turn that ran "
        "no review.",
    )
    consults: list[Consult] = Field(
        default=[],
        description="Every question you put to the advisor before declining a finding, one entry "
        "each. Empty when no advisor is offered or you declined nothing.",
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
    "BuildResult",
    "Consult",
    "Departure",
    "FollowUp",
    "PlanResult",
    "DevOutcome",
    "DevResult",
    "Settlement",
]
