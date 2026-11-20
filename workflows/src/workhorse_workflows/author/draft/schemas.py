"""Where one draft stands in its loop, and how the loop ended."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from workhorse_workflows.kit.telemetry import counter_labels

BUDGET_LABELS = ("reworks", "answers")


class Draft(BaseModel):
    """What the next rework must fix, what the next review verifies, the PM's latest answer, and what the loop has spent."""

    model_config = ConfigDict(frozen=True)

    findings: str = ""
    prior: str = ""
    note: str = ""
    reworks: int = 0
    answers: int = 0


class DraftDone(BaseModel):
    """The loop's outcome: the PM passed the draft, or it stays blocked with the reason."""

    status: Literal["accepted", "blocked"] = "accepted"
    notes: str = ""
    reworks: int = 0
    answers: int = 0


def spent_labels(params: dict[str, Any], prefix: str) -> dict[str, str]:
    """The budget a state's `draft` parameter has spent, as `{prefix}.reworks` and `{prefix}.answers` labels."""
    draft = params.get("draft")
    spent = draft.model_dump() if isinstance(draft, Draft) else draft if isinstance(draft, dict) else {}
    return counter_labels(spent, prefix, BUDGET_LABELS)


__all__ = ["BUDGET_LABELS", "Draft", "DraftDone", "spent_labels"]
