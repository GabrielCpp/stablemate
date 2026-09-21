"""The story spine's models — the three things every per-story flow resolves first."""
from __future__ import annotations

from workhorse_workflows.coder.shared.schemas._base import CoderResult


class StoryPaths(CoderResult):
    """`prepare-story.py` — a slug and an epic resolved to canonical absolute paths."""

    story_path: str = ""
    spec_dir: str = ""
    qa_dir: str = ""
    story_slug: str = ""
    story_epic: str = ""
    story_id: str = ""


class WorkspaceDirs(CoderResult):
    """`resolve-workspace-dirs.py` — every directory an agent turn in this run may read."""

    dirs: list[str] = []


class WorktreeSnapshot(CoderResult):
    """`snapshot_worktrees` — `git status --porcelain` per code repo, keyed by repo path."""

    status: dict[str, str] = {}


class PlanScrub(CoderResult):
    """`scrub_plan_mutations` — what the post-plan-turn clean-tree gate reverted."""

    reverted: dict[str, str] = {}


class SpecsStamped(CoderResult):
    """`stamp-specs.py` — how many spec docs were given an OKF `type` this pass."""

    stamped: int = 0


__all__ = ["PlanScrub", "SpecsStamped", "StoryPaths", "WorkspaceDirs", "WorktreeSnapshot"]
