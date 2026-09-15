"""The QA result-schema types, neutral of any one family that consumes them.

`QaResult`, `QaPlanRun`, `QaStatus` and `StackStatus` started life in
`coder/shared/schemas/qa.py`, declared against `coder`'s own `CoderResult` base. That
was fine while `coder` was the only caller of `qa/runner.py` and `qa/evidence.py` — both
of which already lived outside `coder`, precisely so a second family could call them
without depending on the `coder` package. `okf_builder`'s live-audit lane is that second
caller: it needs the same four types the runner and the evidence gate already return, and
once it imports them, the dependency has to run `okf_builder -> qa`, never
`qa -> coder -> ... -> okf_builder`.

So the types move here, and `coder/shared/schemas/qa.py` re-exports them — every existing
`from workhorse_workflows.coder.shared.schemas.qa import QaResult` import keeps working,
and only the definition moved.

**The base below is not `coder`'s `CoderResult`.** It is copied rather than imported,
because importing it would recreate the exact dependency this split exists to remove.
The two rules that matter for these four types — extra keys ignored, `None` values
dropped so a Python-produced field falls back to its own default, and `blocked` derived
from `status` rather than declared — are the whole of what `CoderResult` gave them, and
are reproduced verbatim here. See `coder/shared/schemas/_base.py` for the fuller
rationale; keep the two in sync by hand if that reasoning ever changes.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: See `coder/shared/schemas/_base.py::BLOCKED_STATUSES` — the same closed vocabulary,
#: kept in sync by hand rather than imported, for the reason in the module docstring.
BLOCKED_STATUSES = frozenset({"blocked", "unfixable", "not_passed", "invalid"})

#: What a QA run came to. Ostler's four states, and the only vocabulary the rolling verdict
#: is ever written from — every gate that hands the loop a verdict writes one of these.
QaStatus = Literal["passed", "failed", "blocked", "invalid"]


class _Result(BaseModel):
    """Extra keys ignored, nulls dropped. See `coder/shared/schemas/_base.py::_Result`."""

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
        """This node cannot finish and something outside it has to decide.

        Derived from `status` rather than declared, so a schema without one is never
        blocked, and a Python-produced status falling back to its pessimistic default is
        not blocked either.
        """
        return str(getattr(self, "status", "")).strip().lower() in BLOCKED_STATUSES

    @property
    def actionable(self) -> list[Any]:
        """The findings a fixer could actually act on — possibly none.

        `findings` is read off the subclass by duck type rather than a shared `Finding`
        class, since neither type declared here carries one; kept only so a caller that
        holds a `QaResult` through a `CoderResult`-typed variable sees the same shape.
        """
        found = getattr(self, "findings", [])
        return [f for f in found if getattr(f, "actionable", False)]


class QaResult(QaBaseResult):
    """The story's running QA verdict — ostler's four states, plus the blank before one.

    `status` starts empty rather than at `invalid`: a caller may read it before anything
    has run, and an unrun gate is not a failed one.
    """

    status: QaStatus | Literal[""] = Field(
        default="",
        description="The story's rolling QA verdict as the turn leaves it. `invalid` while "
        "the plan or its context is being regenerated; `blocked` when the repair itself is.",
    )
    notes: str = Field(default="", description="One line on why the verdict stands there.")


class QaPlanRun(QaResult):
    """`run_qa_plan`'s verdict, plus the ostler payload only it has.

    `ostler` is a subclass field rather than an optional field on `QaResult` for the same
    reason given where this type was first declared: a field on the base is a promise
    every writer of the base must keep, and only the one runner has a payload to report.
    """

    ostler: dict[str, Any] = {}


class StackStatus(QaBaseResult):
    """`ensure_stack`'s account of the durable QA stack: up, adopted, undeclared, or broken.

    `ready` splits the empty manifest in two, because "no stack" means opposite things
    depending on what the book describes — see where this type was first declared for the
    full four-state rationale. `none` and `no` reach the setup-repair loop; `yes` and
    `unneeded` run QA.
    """

    ready: Literal["yes", "no", "none", "unneeded"] = "no"
    app_pid: str = ""
    app_pgid: str = ""
    entry_url: str = ""
    failed_step: str = ""
    notes: str = ""


__all__ = ["BLOCKED_STATUSES", "QaBaseResult", "QaPlanRun", "QaResult", "QaStatus", "StackStatus"]
