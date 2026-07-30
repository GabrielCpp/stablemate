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
`epic_blocked`, `pruned`, `committed`, `qa_flagged` and `has_story` are all the former.
`story_outcome` is `story | done | blocked`, and the whole reason `select-next-story.py`
exists in its current form is that conflating its arms merged an epic with 20 of 21
stories unbuilt — so it stays a string, and it defaults to `blocked`, never to `done`.

`StoryPick` keeps `has_story` alongside `story_outcome` even though the outcome subsumes
it. The YAML emitted both, the labels and anything reading the run record still see both,
and dropping the redundant one would be a narrowing.
"""
from __future__ import annotations

from workhorse_workflows.coder.schemas._base import CoderResult


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
    """`branch-epic.py` — the freshly cut `feat/<epic>`, and the epic it belongs to.

    Always freshly cut: an existing `feat/<epic>` is renamed aside to
    `archive/<epic>-<sha>` rather than resumed. `epic_branch` is `feat/` + the epic even
    when the epic is blank, which is what the YAML emitted and what the PR nodes read.
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
    """

    committed: bool = False


class QaFlagged(CoderResult):
    """`flag-qa-failure.py` — the given-up story was committed behind its `[QA FAILED]` marker.

    False means there was nothing to commit, which is not a failure: the story's status is
    stamped and its slug is in the per-run skip set either way, and those — not the marker
    commit — are what stop it being re-selected.
    """

    qa_flagged: bool = False


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
    "QaFlagged",
    "ReplanResult",
    "StoryBranch",
    "StoryCommitted",
    "StoryPick",
]
