"""The shapes a worktree snapshot and a code-change check record."""
from __future__ import annotations

from workhorse_workflows.coder.shared.schemas._base import CoderResult


class DirtyAtStart(CoderResult):
    """What was already dirty in the repo when this story started."""

    entries: list[str] = []
    notes: str = ""


class PorcelainSnapshot(CoderResult):
    """`snapshot_code_state` — HEAD and `git status --porcelain` per code repo, keyed by repo path."""

    status: dict[str, str] = {}


class CodeChange(CoderResult):
    """`code_changed`: whether a code repo moved since its snapshot, or none could be watched."""

    changed: bool = True


__all__ = ["CodeChange", "DirtyAtStart", "PorcelainSnapshot"]
