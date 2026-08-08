"""Typed intent, plan, and graph snapshots shared by author edit flows."""
from __future__ import annotations

from typing import Literal

from workhorse_workflows.author.shared.schemas._base import AuthorResult


class EditIntent(AuthorResult):
    """The binding operator request that an epic edit plan must satisfy."""

    kind: Literal["epic", "add-story", "remove-story"] = "epic"
    epic: str = ""
    story: str = ""
    bullet_id: str = ""
    source_bullet: str = ""
    from_backlog: bool = False
    change: str = ""
    force: bool = False


class ResolvedBullet(AuthorResult):
    id: str = ""
    source_bullet: str = ""
    from_backlog: bool = False


class SeedSnapshot(AuthorResult):
    id: str = ""
    status: str = ""
    summary: str = ""
    surface: str = ""
    legacy_surface: str = ""
    backing: str = ""
    prerequisites: str = ""
    source_bullet: str = ""
    frozen: bool = False


class StorySnapshot(AuthorResult):
    slug: str = ""
    title: str = ""
    status: str = ""
    covers: list[str] = []
    depends: list[str] = []
    story_path: str = ""
    body_hash: str = ""
    frozen: bool = False


class MilestoneSnapshot(AuthorResult):
    name: str = ""
    source_items: list[str] = []
    epics: list[str] = []


class EpicSnapshot(AuthorResult):
    epic: str = ""
    epic_dir: str = ""
    epics_dir: str = ""
    title: str = ""
    epic_hash: str = ""
    seeds: list[SeedSnapshot] = []
    stories: list[StorySnapshot] = []
    milestones: list[MilestoneSnapshot] = []


class SeedChange(AuthorResult):
    action: Literal["add", "update", "remove"] = "add"
    id: str = ""
    status: str = "researched"
    summary: str = ""
    surface: str = ""
    legacy_surface: str = ""
    backing: str = ""
    prerequisites: str = ""
    source_bullet: str = ""
    disposition: Literal["retain", "drop"] = "retain"
    reason: str = ""


class StoryChange(AuthorResult):
    action: Literal["add", "update", "remove"] = "add"
    slug: str = ""
    title: str = ""
    covers: list[str] = []
    depends: list[str] = []
    rewrite: bool = False


class EpicEditPlan(AuthorResult):
    """A complete replacement plan, validated before any graph write."""

    status: Literal["complete", "blocked"] = "blocked"
    epic: str = ""
    delete_epic: bool = False
    summary: str = ""
    journey_changes: list[str] = []
    seed_changes: list[SeedChange] = []
    story_changes: list[StoryChange] = []
    affected_stories: list[str] = []
    notes: str = ""


class AppliedEpicEdit(AuthorResult):
    changed: bool = False
    epic: str = ""
    epic_dir: str = ""
    deleted: bool = False
    affected_stories: list[str] = []
    removed_stories: list[str] = []


class EpicEditReview(AuthorResult):
    status: Literal["approved", "needs_rework", "blocked"] = "needs_rework"
    notes: str = ""


class EpicRewriteResult(AuthorResult):
    status: Literal["complete", "blocked"] = "blocked"
    notes: str = ""


__all__ = [
    "AppliedEpicEdit",
    "EditIntent",
    "EpicEditPlan",
    "EpicEditReview",
    "EpicRewriteResult",
    "EpicSnapshot",
    "MilestoneSnapshot",
    "ResolvedBullet",
    "SeedChange",
    "SeedSnapshot",
    "StoryChange",
    "StorySnapshot",
]
