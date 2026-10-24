"""The backlog as a worklist: what was drawn from it, what it seeded, what it recorded."""
from __future__ import annotations

from workhorse_workflows.coder.shared.schemas._base import CoderResult
from workhorse_workflows.coder.shared.schemas.qa import BacklogDrain


class FiledBacklog(CoderResult):
    """The open `qa` records of the run's workspace, and the items a QA run left to file, each by id."""

    filed: dict[str, str] = {}
    items: dict[str, str] = {}


class FixPick(CoderResult):
    """`select_fix_item` — the next drainable `qa` record, or "the pool is dry"."""

    has_fix: bool = False
    record_id: str = ""
    repo: str = ""
    area: str = ""
    summary: str = ""
    body: str = ""
    reason: str = ""


class FixStorySeed(CoderResult):
    """`seed_fix_story` — the single-AC story a drained record became."""

    epic: str = ""
    epic_dir: str = ""
    story_slug: str = ""
    story_id: str = ""
    story_dir: str = ""
    story_path: str = ""
    record_id: str = ""
    reason: str = ""


class FixClosed(CoderResult):
    """`close_fix_item` — the shipped fix's record is closed as done on the register."""

    closed: bool = False
    record_id: str = ""
    reason: str = ""


__all__ = ["BacklogDrain", "FiledBacklog", "FixClosed", "FixPick", "FixStorySeed"]
