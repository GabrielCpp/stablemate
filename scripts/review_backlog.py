"""Walking a committed backlog too large to review at once, one reviewable commit range at a time."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import strict_scope
from review_git import first_parent_commits, git, is_ancestor
from review_outcome import Block, GiveUp, Notice, Outcome
from review_run import PendingChange, model_for, plan_review, run_batches, unfinished_reason
from review_state import HOOK_STATE_FILE, GateState, save_state
from review_verdict import Reviewer, Verdict


@dataclass(frozen=True)
class BacklogWalk:
    state: GateState
    change: PendingChange
    skip_notices: tuple[str, ...]
    block: Block | None


@dataclass(frozen=True)
class RangeStep:
    state: GateState
    skip_notice: str | None
    block: Block | None


def in_backlog(repo: Path, state: GateState, change: PendingChange) -> bool:
    return (
        state.base_head is not None
        and state.base_tree == change.base_tree
        and state.base_head != change.head
        and is_ancestor(repo, state.base_head, change.head)
    )


def change_up_to_commit(repo: Path, base_tree: str, commit: str) -> PendingChange:
    tree = git(repo, "rev-parse", f"{commit}^{{tree}}")
    names = git(repo, "diff", "--name-only", base_tree, tree)
    return PendingChange(head=commit, base_tree=base_tree, tree=tree, paths=tuple(names.splitlines()))


def change_since(repo: Path, reviewed: GateState, change: PendingChange) -> PendingChange:
    base_tree = reviewed.base_tree or change.base_tree
    names = git(repo, "diff", "--name-only", base_tree, change.tree)
    return PendingChange(head=change.head, base_tree=base_tree, tree=change.tree, paths=tuple(names.splitlines()))


def widest_range(repo: Path, base_tree: str, commits: list[str], rubric: str) -> PendingChange | None:
    fitting = None
    for commit in commits:
        candidate = change_up_to_commit(repo, base_tree, commit)
        if plan_review(repo, candidate, rubric).too_large:
            break
        fitting = candidate
    return fitting


def range_block_reason(verdict: Verdict, label: str) -> str:
    return "\n".join([
        f"The review gate ({verdict.model}) found problems in commits {label}, which are already committed.",
        "Fix each one in a new commit, then stop again. The gate has moved past these commits,"
        " so it reviews your fix with the rest of your diff.",
        *(f"- {finding.render()}" for finding in verdict.findings),
    ])


def review_next_range(
    repo: Path,
    scope: strict_scope.StrictScope,
    state: GateState,
    change: PendingChange,
    rubric: str,
    reviewer: Reviewer,
) -> RangeStep:
    base_head = state.base_head or change.head
    commits = first_parent_commits(repo, base_head, change.head)
    fitting = widest_range(repo, change.base_tree, commits, rubric)
    if fitting is None:
        alone = change_up_to_commit(repo, change.base_tree, commits[0])
        skip_notice = f"Commit {commits[0][:8]} is too large to review on its own, so it goes through unreviewed."
        return RangeStep(GateState(alone.tree, alone.head, 0), skip_notice, None)
    advanced = GateState(fitting.tree, fitting.head, 0)
    if not any(scope.contains(path) for path in fitting.paths):
        return RangeStep(advanced, None, None)
    review = run_batches(rubric, plan_review(repo, fitting, rubric), reviewer, model_for(state))
    if review.unreviewed is not None:
        return RangeStep(state, None, Block(unfinished_reason(review)))
    if review.verdict.passed:
        return RangeStep(advanced, None, None)
    label = f"{base_head[:8]}..{fitting.head[:8]}"
    return RangeStep(advanced, None, Block(range_block_reason(review.verdict, label)))


def walk_backlog(
    repo: Path,
    scope: strict_scope.StrictScope,
    state: GateState,
    change: PendingChange,
    rubric: str,
    reviewer: Reviewer,
) -> BacklogWalk:
    """Review the committed backlog one range at a time until what is left fits one review, saving the gate's state after each range.

    The walk keeps the head and the tree *change* read at the stop, so a commit or an edit made during the walk waits for the next stop.
    """
    skip_notices: list[str] = []
    while in_backlog(repo, state, change) and plan_review(repo, change, rubric).too_large:
        step = review_next_range(repo, scope, state, change, rubric, reviewer)
        save_state(repo, HOOK_STATE_FILE, step.state)
        if step.skip_notice is not None:
            skip_notices.append(step.skip_notice)
        if step.block is not None:
            return BacklogWalk(step.state, change, tuple(skip_notices), step.block)
        state = step.state
        change = change_since(repo, step.state, change)
    return BacklogWalk(state, change, tuple(skip_notices), None)


def with_skip_notices(outcome: Outcome, skip_notices: tuple[str, ...]) -> Outcome:
    if not skip_notices:
        return outcome
    if isinstance(outcome, Block):
        return Block("\n".join([*skip_notices, outcome.reason]))
    if isinstance(outcome, GiveUp):
        return GiveUp("\n".join([*skip_notices, outcome.message]))
    if isinstance(outcome, Notice):
        return Notice("\n".join([*skip_notices, outcome.message]))
    return Notice("\n".join(skip_notices))
