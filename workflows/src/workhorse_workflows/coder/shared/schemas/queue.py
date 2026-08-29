"""The main graph's spine: which epic, which story, on what branch, and what it recorded.

Ported from the nine queue scripts the main graph runs between its sub-flows —
`init-base.py`, `branch-story.py`, `select-next-epic.py`, `branch-epic.py`,
`select-next-story.py`, `flag-epic-blocked.py`, `prune-epic.py`, `commit-story.py` and
`flag-qa-failure.py`. They are one subject because they are one loop: the epic queue is
walked front-to-back, each epic's stories are walked in dependency order, and every
outcome — passed, given up, or set aside — is recorded back onto the queue so the next
pass sees it.

**The `yes`/`no` scalars are bools, and the tri-states are `Literal`s.** A two-state
answer whose blank means "no" is a bool: `has_epic`, `epic_blocked`, `pruned` and
`committed`. A status is a `Literal`, defaulted or not by who produces it (`_base.py`).
Every status in this module but `WorktreeSettled`'s is Python-produced, so it carries a
default and the default is the pessimistic arm — `story_outcome` defaults to `blocked`,
never to `done`, because conflating its arms is what merged an epic with 20 of 21 stories
unbuilt.

`has_story` is gone. It answered `story_outcome == "story"` and nothing else, and a
second field saying the same thing is a second field to get wrong: the whole defect the
outcome exists to prevent is a reader that treats "no story" as one answer.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from workhorse_workflows.coder.shared.schemas._base import CoderResult


class RunScope(CoderResult):
    """`begin_run` — the per-run skip state a previous run left in this run dir.

    `cleared` names the files that were dropped, and is empty on a first run. It exists so
    the run record shows the clearing happened: an epic that vanishes from the queue on
    pass one and reappears on pass two is otherwise indistinguishable from a queue bug.
    """

    cleared: list[str] = []


class BaseBranch(CoderResult):
    """`init-base.py` — the branch an epic's PR will be opened against.

    The current branch when that is a real base, and the repo's trunk when HEAD is
    detached, empty, or still sitting on a `feat/`/`rewrite/` branch a prior run left
    behind. Never blank: the trunk resolution falls through to `main`.
    """

    base_branch: str = ""


class StoryBranch(CoderResult):
    """`branch-story.py` — the branch cut for a single story, and where it was cut.

    `repos` is the list of workspace repos actually branched, docs root first. It is a
    real `list[str]` here; the YAML carried it as a JSON string only because a workflow
    var is a string.
    """

    base_branch: str = ""
    story_branch: str = ""
    repos: list[str] = []


class EpicPick(CoderResult):
    """`select-next-epic.py` — the front epic of the queue that is not set aside.

    `has_epic` false ends the run: either the queue is empty (every epic merged) or every
    queued epic was set aside this run. `reason` says which, and it is the only place that
    distinction is recorded — both look identical from the transition alone.
    """

    has_epic: bool = False
    epic: str = ""
    reason: str = ""


class EpicBranch(CoderResult):
    """`branch-epic.py` — the `feat/<epic>` this run is on, and the epic it belongs to.

    Cut from HEAD when it does not exist. When it does, the run either continues on it
    (this working tree already had it, or it is merged into the base and the name is
    free to reuse) or refuses — a branch another working tree holds, or one carrying
    unmerged work nobody claimed, is not this run's to take. See
    `queue._claim_epic_branch`.

    `epic_branch` is `feat/` + the epic even when the epic is blank, which is what the
    YAML emitted and what the PR nodes read.
    """

    working_epic: str = ""
    epic_branch: str = ""


class StoryPick(CoderResult):
    """`select-next-story.py` — the next runnable story in an epic, or why there is none.

    `story_outcome` is the field the graph branches on: `story` builds it, `done` prunes
    and merges the epic, `blocked` sets the epic aside for this run. It defaults to
    `blocked` so an unanswered selection can never be the reason an epic is merged.

    `progress` and `remaining_count` are the shared worklist snapshot — `"3/12"` and
    `9` — folded into every outcome so the run's labels carry queue progress whichever
    way the selection went.
    """

    story_outcome: Literal["story", "done", "blocked"] = "blocked"
    story_path: str = ""
    spec_dir: str = ""
    story_slug: str = ""
    # The minted id from the story's frontmatter — the identity commit trailers carry.
    # Empty on a book that predates minted ids; consumers fall back to the slug.
    story_id: str = ""
    epic: str = ""
    reason: str = ""
    progress: str = ""
    remaining_count: int = 0


class EpicBlocked(CoderResult):
    """`flag-epic-blocked.py` — the epic was set aside for the rest of this run.

    `blocked_epics` stays the comma-joined string the YAML emitted rather than becoming a
    list: it is a human-readable summary for the run record, and nothing branches on it.
    The authoritative set is the file in the run dir that `select_epic` reads.
    """

    epic_blocked: bool = False
    blocked_epics: str = ""
    reason: str = ""


class EpicPruned(CoderResult):
    """`prune-epic.py` — the merged epic was popped off the front of the queue.

    `pruned` false is not a failure and nothing branches on it: a stale queue entry costs
    one extra no-op PR/merge cycle, which is why the script was best-effort throughout.
    """

    pruned: bool = False


class StoryCommitted(CoderResult):
    """`commit-story.py` — did the story's *work* land in any affected repo?

    Deliberately not "did anything get committed": the `QA passed` status stamp is
    committed separately and is excluded from this answer, because every passing story
    writes one — counting it would make every story look like a story that did work.

    `superseded_outcome` is the other half of that guard's question. It is narrower than
    "was a stamp written", which every passing story does: it is "did this stamp replace a
    *previous attempt's* outcome" — a give-up, a docs block, an interrupted run — as
    opposed to a story that arrived `Not started` and has never been built. Re-running a
    story whose work already landed under a failure marker is the most valuable thing the
    loop does and it commits nothing by construction, so counting it as churn ends the run
    for succeeding. A never-attempted story that builds nothing is the opposite reading and
    still counts, which is what keeps the guard able to catch a dev phase that has quietly
    stopped producing code.
    """

    committed: bool = False
    superseded_outcome: bool = False


class WorktreeCleanliness(CoderResult):
    """`check_repos_clean` — has the agent left uncommitted work behind in any repo?

    The reading that replaced the workflow's own `git commit -a`. Committing on the
    agent's behalf meant the workflow decided the subject, the scope and the boundary of
    every story commit from outside the work, and swept whatever else was in the tree into
    it. The agent commits at will now, and this node checks the one thing that has to be
    true afterwards: nothing this story produced is still only on disk.

    `dirty` is `repo:path`, one entry per uncommitted path, already **minus** what
    `snapshot_worktree_state` recorded as dirty before the story started and which the
    story has not touched since — an operator's leftovers are not the agent's to answer
    for. The subtraction only ever shrinks by mistake; see `shared/worktree.py`.
    """

    clean: bool = False
    dirty: list[str] = []
    repos: list[str] = []


class WorktreeSettled(CoderResult):
    """`settle-worktree.md` — the one lap given to work the story did not record.

    `blocked` is the interesting arm and it is the honest one: the tree holds something
    the agent did not write and will not speak for, which is an operator's call, not a
    reason to commit a stranger's changes under this story's name.
    """

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
    """`stamp_story_passed` — the story's `QA passed` status line, and whether it moved.

    Queue integrity rather than development work, which is why it stayed a node when the
    commits left: nothing else on the success path writes that status, and story selection
    reads the status, not the git log. An agent that forgets it re-runs the story forever
    and the epic never completes, and the failure is invisible until it does not.

    `superseded_outcome` is the narrower fact `StoryCommitted` carried under the same
    name: this stamp replaced a *previous attempt's* outcome — a give-up, a docs block, an
    interrupted run — rather than the `Not started` a never-built story carries.
    """

    stamped: bool = False
    superseded_outcome: bool = False


class ReplanResult(CoderResult):
    """`replan_epic`'s reply — the rewrite of the epic the operator's answer forced.

    Unbranched, like `MergeFixResult`: the YAML declared `replan_result` and then went
    straight back to `select_story`, because the evidence that the replan worked is the
    queue the next pick reads, not the turn's summary of itself.
    """

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
