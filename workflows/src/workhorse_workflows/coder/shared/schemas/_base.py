"""The base every agent reply and node return in this workflow derives from."""
from __future__ import annotations

from pydantic import Field

from workhorse_workflows.kit.result import Result as _Result

BLOCKED_STATUSES = frozenset({"blocked", "unfixable", "not_passed", "invalid"})


class Finding(_Result):
    """One defect with somewhere to go: where it is, and what has to change there."""

    target: str = Field(
        default="",
        description="Where the defect is, as one string: a repo-relative path, a "
        "`repo/path:line`, or a spec/AC and scenario id. Required — a finding that names no "
        "place to go is a complaint, and the machine downstream cannot route it.",
    )
    issue: str = Field(default="", description="What is wrong there.")
    repair: str = Field(
        default="",
        description="The smallest acceptable change that closes it. Required for the same "
        "reason as `target`: a finding that nominates no change bills a repair budget and "
        "buys nothing.",
    )

    @property
    def actionable(self) -> bool:
        """Both halves present."""
        return bool(self.target.strip() and self.repair.strip())


class CoderResult(_Result):
    """Base for every agent reply and node return in the coder workflow."""

    @property
    def blocked(self) -> bool:
        """This node cannot finish and something outside it has to decide."""
        return str(getattr(self, "status", "")).strip().lower() in BLOCKED_STATUSES

    @property
    def actionable(self) -> list[Finding]:
        """The findings a fixer could actually act on — possibly none."""
        found = getattr(self, "findings", [])
        return [f for f in found if isinstance(f, Finding) and f.actionable]


__all__ = ["BLOCKED_STATUSES", "CoderResult", "Finding"]
