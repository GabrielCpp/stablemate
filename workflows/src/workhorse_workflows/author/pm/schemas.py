"""What the PM's turns return, and what its flows hand back."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from workhorse.pyflow import dry_run
from workhorse_workflows.author.shared.schemas import AuthorResult


class Finding(BaseModel):
    """One defect, with where it lives and what would repair it."""

    target: str
    issue: str
    repair: str


class AngleVerdict(BaseModel):
    """One angle's judgment of the subject."""

    angle: str
    status: Literal["passed", "failed"]
    findings: list[Finding] = Field(default_factory=list)
    note: str = ""


@dry_run(angles=[])
class Verdict(BaseModel):
    """A review turn's reply: one verdict for every angle of the stage."""

    angles: list[AngleVerdict]


class PMFinding(Finding):
    """A finding, with the angle that raised it."""

    angle: str


class PMReceipt(AuthorResult):
    """`record_pm_receipt`: where the pass was written and what it was bound to."""

    path: str = ""
    digest: str = ""


class PMResult(AuthorResult):
    """`PMReview`: whether every angle passed, and the findings when one did not."""

    stage: str = ""
    passed: bool = False
    findings: list[PMFinding] = []
    notes: str = ""
    receipt_path: str = ""


@dry_run(kind="answered", answer="", reason="")
class Answer(BaseModel):
    """A gap-answer turn's reply: the decision, or a request for the operator."""

    kind: Literal["answered", "amendment"]
    answer: str = ""
    reason: str = ""


class LedgerEntry(AuthorResult):
    """`append_ledger`: where the entry was recorded."""

    path: str = ""


class GapAnswered(AuthorResult):
    """`GapAnswer`: the answer to a writer's question, and who gave it."""

    kind: Literal["answered", "amendment"] = "answered"
    answer: str = ""
    by: Literal["pm", "human"] = "pm"
    note: str = ""


__all__ = [
    "Answer",
    "AngleVerdict",
    "Finding",
    "GapAnswered",
    "LedgerEntry",
    "PMFinding",
    "PMReceipt",
    "PMResult",
    "Verdict",
]
