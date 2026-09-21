"""The backlog as a worklist: what was drawn from it, what it seeded, what it recorded."""
from __future__ import annotations

from workhorse_workflows.coder.shared.schemas._base import CoderResult
from workhorse_workflows.coder.shared.schemas.qa import BacklogDrain


class FixPick(CoderResult):
    """`select-next-fix-item.py` — the next drainable bullet, or "the pool is dry"."""

    has_fix: bool = False
    fix_bullet_id: str = ""
    fix_bullet_text: str = ""
    reason: str = ""


class FixStorySeed(CoderResult):
    """`seed-fix-story.py` — the single-AC story a drained bullet became."""

    epic: str = ""
    epic_dir: str = ""
    story_slug: str = ""
    story_dir: str = ""
    story_path: str = ""
    bullet_id: str = ""
    reason: str = ""


class FixPruned(CoderResult):
    """`prune-fix-item.py` — the shipped fix's bullet is gone from the backlog."""

    pruned: bool = False
    bullet_id: str = ""
    reason: str = ""


class FixBlocked(CoderResult):
    """`mark-fix-blocked.py` — the stuck fix's bullet is annotated in place, not removed."""

    marked: bool = False
    bullet_id: str = ""
    reason: str = ""


__all__ = ["BacklogDrain", "FixBlocked", "FixPick", "FixPruned", "FixStorySeed"]
