"""Cumulative recovery-wait budgets shared by one agent-node visit."""
from __future__ import annotations

import math
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Literal

from workhorse.config_run import AgentResilience
from workhorse.runner.failure import BackendInvocationError

WaitKind = Literal["cap", "retry", "reframe", "exec-retry"]


class RecoveryWaitBudgetExceeded(BackendInvocationError):
    """A node spent the cumulative sleep allowance for one recovery category."""

    def __init__(self, kind: WaitKind, budget_s: float, spent_s: float, requested_s: float):
        self.kind = kind
        self.budget_s = budget_s
        self.spent_s = spent_s
        self.requested_s = requested_s
        super().__init__(
            f"{kind} wait budget exhausted: spent {spent_s:g}s of {budget_s:g}s; "
            f"next recovery requires {requested_s:g}s",
            transient=False,
        )


@dataclass(slots=True)
class RecoveryWaitBudget:
    """Mutable consumption ledger whose immutable limits come from run configuration."""

    limits: dict[WaitKind, float]
    spent: dict[WaitKind, float] = field(default_factory=dict)

    @classmethod
    def from_resilience(cls, resilience: AgentResilience) -> RecoveryWaitBudget:
        return cls(
            limits={
                "cap": resilience.cap_wait_budget_s,
                "retry": resilience.retry_wait_budget_s,
                "reframe": resilience.reframe_wait_budget_s,
                "exec-retry": resilience.exec_retry_wait_budget_s,
            }
        )

    def consume(self, kind: WaitKind, requested_s: float) -> None:
        """Reserve one sleep, raising before it would exceed the category allowance."""
        budget_s = self.limits[kind]
        spent_s = self.spent.get(kind, 0.0)
        if (
            not math.isfinite(budget_s)
            or budget_s < 0
            or not math.isfinite(requested_s)
            or requested_s < 0
            or requested_s > max(0.0, budget_s - spent_s)
        ):
            raise RecoveryWaitBudgetExceeded(kind, budget_s, spent_s, requested_s)
        self.spent[kind] = spent_s + requested_s


_ACTIVE: ContextVar[RecoveryWaitBudget | None] = ContextVar(
    "workhorse_recovery_wait_budget", default=None
)


def active_recovery_wait_budget() -> RecoveryWaitBudget | None:
    """The current agent-node ledger, if execution is inside one."""
    return _ACTIVE.get()


@contextmanager
def recovery_wait_scope(budget: RecoveryWaitBudget) -> Iterator[None]:
    """Make one ledger visible through nested backend/process calls."""
    token = _ACTIVE.set(budget)
    try:
        yield
    finally:
        _ACTIVE.reset(token)


__all__ = [
    "RecoveryWaitBudget",
    "RecoveryWaitBudgetExceeded",
    "active_recovery_wait_budget",
    "recovery_wait_scope",
]
