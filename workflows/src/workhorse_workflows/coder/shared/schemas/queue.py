"""The main graph's spine: which epic, which story, on what branch, and what it recorded."""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from workhorse_workflows.coder.shared.schemas._base import CoderResult


class RunScope(CoderResult):
    """`begin_run` — the per-run skip state a previous run left in this run dir."""

    cleared: list[str] = []


class BaseBranch(CoderResult):
    """`init-base.py` — the branch an epic's PR will be opened against."""

    base_branch: str = ""


class StoryBranch(CoderResult):
    """`branch-story.py` — the branch cut for a single story, and where it was cut."""

    base_branch: str = ""
    story_branch: str = ""
    repos: list[str] = []


class EpicPick(CoderResult):
    """`select-next-epic.py` — the front epic of the queue that is not set aside."""

    has_epic: bool = False
    epic: str = ""
    reason: str = ""


class EpicBranch(CoderResult):
    """`branch-epic.py` — the `feat/<epic>` this run is on, and the epic it belongs to."""

    working_epic: str = ""
    epic_branch: str = ""


class StoryPick(CoderResult):
    """`select-next-story.py` — the next runnable story in an epic, or why there is none."""

    story_outcome: Literal["story", "done", "blocked"] = "blocked"
    story_path: str = ""
    spec_dir: str = ""
    story_slug: str = ""
    story_id: str = ""
    epic: str = ""
    reason: str = ""
    progress: str = ""
    remaining_count: int = 0


class EpicBlocked(CoderResult):
    """`flag-epic-blocked.py` — the epic was set aside for the rest of this run."""

    epic_blocked: bool = False
    blocked_epics: str = ""
    reason: str = ""


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


class WorktreeSettled(CoderResult):
    """`settle-worktree.md` — the one lap given to work the story did not record."""

    status: Literal["settled", "blocked"] = Field(
        description="`settled` — every path you were shown is either committed or was "
        "deliberately left, and the tree holds nothing of this story's that is not "
        "recorded. `blocked` — something on that list needs a human: you cannot tell whose "
        "it is, committing it would be wrong, or the commit itself failed. Return `blocked` "
        "rather than guessing: the run parks for an operator, which costs ten minutes; a "
        "commit of someone else's work under this story's name costs considerably more.",
    )
    notes: str = Field(
        default="",
        description="What you committed, per package — or which paths you left and why they "
        "are not yours.",
    )


class StoryStamped(CoderResult):
    """`stamp_story_passed` — the story's `QA passed` status line, and whether it moved."""

    stamped: bool = False
    superseded_outcome: bool = False


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
    "EpicBlocked",
    "EpicBranch",
    "EpicPick",
    "EpicPruned",
    "ReplanResult",
    "RunScope",
    "StoryBranch",
    "StoryCommitted",
    "StoryPick",
    "StoryStamped",
    "WorktreeCleanliness",
    "WorktreeSettled",
]
