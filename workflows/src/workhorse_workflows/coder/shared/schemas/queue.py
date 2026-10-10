"""The main graph's spine: which stories the run works, on what branch, and what it recorded."""
from __future__ import annotations

from typing import Literal

from pydantic import Field
from workhorse.pyflow import dry_run

from workhorse_workflows.coder.shared.schemas._base import CoderResult


class RunScope(CoderResult):
    """`begin_run` — the state a previous run left in this run dir, now cleared."""

    cleared: list[str] = []


class LaunchEntry(CoderResult):
    """One story the launch filed: its slug, its ostler id, and the epic it runs under."""

    slug: str = ""
    id: str = ""
    epic: str = ""


class LaunchSet(CoderResult):
    """`resolve_launch` — every story this run works, in the order it works them."""

    mode: Literal["epic", "story"] = "epic"
    entries: list[LaunchEntry] = []


class BaseBranch(CoderResult):
    """`init-base.py` — the branch an epic's PR will be opened against."""

    base_branch: str = ""


class StoryBranch(CoderResult):
    """`branch-story.py` — the branch cut for a single story, and where it was cut."""

    base_branch: str = ""
    story_branch: str = ""
    repos: list[str] = []


class EpicBranch(CoderResult):
    """`branch-epic.py` — the `feat/<epic>` this run is on, and the epic it belongs to."""

    working_epic: str = ""
    epic_branch: str = ""


class EpicPruned(CoderResult):
    """`prune-epic.py` — the merged epic was popped off the front of the queue."""

    pruned: bool = False


class StoryCommitted(CoderResult):
    """`commit-story.py` — did the story's *work* land in any affected repo?"""

    committed: bool = False
    superseded_outcome: bool = False


class WorktreeCleanliness(CoderResult):
    """`check_repos_clean` — has the agent left uncommitted work behind in any repo?"""

    clean: bool = False
    dirty: list[str] = []
    repos: list[str] = []


class StoryStamped(CoderResult):
    """`stamp_story_passed` — the story's `QA passed` status line, and whether it moved."""

    stamped: bool = False
    superseded_outcome: bool = False


@dry_run(status="done")
class ReplanResult(CoderResult):
    """`replan_epic`'s reply — the rewrite of the epic the operator's answer forced."""

    status: Literal["done", "blocked"] = Field(
        description="`done` when the epic is re-grounded. `blocked` rather than rewriting it "
        "around a guess: the workflow re-reads these stories immediately after this stage, "
        "so an epic grounded in an invention is executed as though it were ground truth.",
    )
    notes: str = Field(
        default="",
        description="One line on what was re-grounded, or the specific thing the operator's "
        "answer left undecided.",
    )


__all__ = [
    "BaseBranch",
    "EpicBranch",
    "EpicPruned",
    "LaunchEntry",
    "LaunchSet",
    "ReplanResult",
    "RunScope",
    "StoryBranch",
    "StoryCommitted",
    "StoryStamped",
    "WorktreeCleanliness",
]
