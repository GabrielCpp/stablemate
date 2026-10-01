"""The shapes a worktree snapshot and a plan scrub record."""
from __future__ import annotations

from workhorse_workflows.coder.shared.schemas._base import CoderResult


class DirtyAtStart(CoderResult):
    """What was already dirty in the repo when this story started."""

    entries: list[str] = []
    notes: str = ""


class PorcelainSnapshot(CoderResult):
    """`snapshot_worktrees` — `git status --porcelain` per code repo, keyed by repo path."""

    status: dict[str, str] = {}


class PlanScrub(CoderResult):
    """`scrub_plan_mutations` — what the post-plan-turn clean-tree gate reverted."""

    reverted: dict[str, str] = {}


__all__ = ["DirtyAtStart", "PlanScrub", "PorcelainSnapshot"]
