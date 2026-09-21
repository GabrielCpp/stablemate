"""The QA result-schema types, neutral of any one family that consumes them."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

BLOCKED_STATUSES = frozenset({"blocked", "unfixable", "not_passed", "invalid"})

QaStatus = Literal["passed", "failed", "blocked", "invalid"]


class _Result(BaseModel):
    """Extra keys ignored, nulls dropped."""

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _drop_nulls(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if v is not None}
        return data


class QaBaseResult(_Result):
    """Neutral counterpart of `coder`'s `CoderResult` — see the module docstring."""

    @property
    def blocked(self) -> bool:
        """This node cannot finish and something outside it has to decide."""
        return str(getattr(self, "status", "")).strip().lower() in BLOCKED_STATUSES

    @property
    def actionable(self) -> list[Any]:
        """The findings a fixer could actually act on — possibly none."""
        found = getattr(self, "findings", [])
        return [f for f in found if getattr(f, "actionable", False)]


class QaResult(QaBaseResult):
    """The story's running QA verdict — ostler's four states, plus the blank before one."""

    status: QaStatus | Literal[""] = Field(
        default="",
        description="The story's rolling QA verdict as the turn leaves it. `invalid` while "
        "the plan or its context is being regenerated; `blocked` when the repair itself is.",
    )
    notes: str = Field(default="", description="One line on why the verdict stands there.")


class QaPlanRun(QaResult):
    """`run_qa_plan`'s verdict, plus the ostler payload only it has."""

    ostler: dict[str, Any] = {}


class StackStatus(QaBaseResult):
    """`ensure_stack`'s account of the durable QA stack: up, adopted, undeclared, or broken."""

    ready: Literal["yes", "no", "none", "unneeded"] = "no"
    app_pid: str = ""
    app_pgid: str = ""
    entry_url: str = ""
    failed_step: str = ""
    notes: str = ""


__all__ = ["BLOCKED_STATUSES", "QaBaseResult", "QaPlanRun", "QaResult", "QaStatus", "StackStatus"]
