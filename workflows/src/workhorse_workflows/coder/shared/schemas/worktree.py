"""The shapes a worktree snapshot and a proven-state record."""
from __future__ import annotations

from workhorse_workflows.coder.shared.schemas._base import CoderResult


class DirtyAtStart(CoderResult):
    """What was already dirty in the repo when this story started."""

    entries: list[str] = []
    notes: str = ""


class ProvenState(CoderResult):
    """`snapshot_proven_state` — each leftover path with the digest it held when QA passed, as `<repo>:<path>` NUL digest."""

    entries: list[str] = []


__all__ = ["DirtyAtStart", "ProvenState"]
