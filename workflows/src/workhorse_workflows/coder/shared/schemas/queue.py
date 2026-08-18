"""The main graph's spine: which epic, which story, on what branch, and what it recorded.

Ported from the nine queue scripts the main graph runs between its sub-flows —
`init-base.py`, `branch-story.py`, `select-next-epic.py`, `branch-epic.py`,
`select-next-story.py`, `flag-epic-blocked.py`, `prune-epic.py`, `commit-story.py` and
`flag-qa-failure.py`. They are one subject because they are one loop: the epic queue is
walked front-to-back, each epic's stories are walked in dependency order, and every
outcome — passed, given up, or set aside — is recorded back onto the queue so the next
pass sees it.

**The `yes`/`no` scalars become bools, and `story_outcome` does not.** That is `ci.py`'s
rule applied again: a two-state answer whose blank means "no" is a bool, and a tri-state
whose YAML `default:` arm is the pessimistic one stays a string. `has_epic`,
`epic_blocked`, `pruned`, `committed` and `has_story` are all the former.
`story_outcome` is `story | done | blocked`, and the whole reason `select-next-story.py`
exists in its current form is that conflating its arms merged an epic with 20 of 21
stories unbuilt — so it stays a string, and it defaults to `blocked`, never to `done`.

`StoryPick` keeps `has_story` alongside `story_outcome` even though the outcome subsumes
it. The YAML emitted both, the labels and anything reading the run record still see both,
and dropping the redundant one would be a narrowing.
"""
from __future__ import annotations

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
    `"9"` — folded into every outcome so the run's labels carry queue progress whichever
    way the selection went.
    """

    has_story: bool = False
    story_outcome: str = "blocked"
    story_path: str = ""
    spec_dir: str = ""
    story_slug: str = ""
    epic: str = ""
    reason: str = ""
    progress: str = ""
    remaining_count: str = ""


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
    committed separately and is excluded from this answer, because the zero-diff churn
    guard counts consecutive no-op story commits and a stamp every passing story makes
    would keep the guard from ever tripping.

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

    status: str = ""
    notes: str = ""


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

    status: str = ""
    notes: str = ""


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
