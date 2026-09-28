#!/usr/bin/env python3
"""Hold the implementing agent at Stop until a fresh reviewer passes its diff."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import strict_scope
from claude_reviewer import claude_reviewer
from review_backlog import walk_backlog, with_skip_notices
from review_git import git, is_ancestor, snapshot_tree, tree_exists
from review_run import (
    ROUNDS_BEFORE_TIEBREAK,
    TIEBREAK_MODEL,
    BatchedVerdict,
    Block,
    GiveUp,
    Outcome,
    PendingChange,
    model_for,
    plan_review,
    run_batches,
    unfinished_reason,
)
from review_state import BASE_STATE_FILE, HOOK_STATE_FILE, GateState, load_state, next_state, save_state
from review_verdict import Reviewer, Verdict

REPO = Path(__file__).resolve().parents[1]
RUBRIC_PATH = Path(__file__).resolve().with_name("review_gate_prompt.md")
MAX_BLOCKED_ROUNDS = 10


@dataclass(frozen=True)
class StopEvent:
    cwd: Path


def parse_stop_event(text: str) -> StopEvent | None:
    try:
        payload: object = json.loads(text or "{}")
    except json.JSONDecodeError:
        return None
    cwd = payload.get("cwd") if isinstance(payload, dict) else None
    return StopEvent(cwd=Path(cwd)) if isinstance(cwd, str) else None


def resolve_base(repo: Path, state: GateState, head: str, base: str | None) -> str:
    if base is not None:
        return git(repo, "rev-parse", f"{base}^{{tree}}")
    pinned = state.base_tree
    if pinned and tree_exists(repo, pinned):
        if state.blocked_rounds > 0:
            return pinned
        if state.base_head and is_ancestor(repo, state.base_head, head):
            return pinned
    return git(repo, "rev-parse", "HEAD^{tree}")


def pending_change(repo: Path, state: GateState, base: str | None) -> PendingChange:
    head = git(repo, "rev-parse", "HEAD")
    base_tree = resolve_base(repo, state, head, base)
    tree = snapshot_tree(repo)
    names = git(repo, "diff", "--name-only", base_tree, tree)
    return PendingChange(head=head, base_tree=base_tree, tree=tree, paths=tuple(names.splitlines()))


def review_change(repo: Path, change: PendingChange, reviewer: Reviewer, model: str) -> BatchedVerdict:
    rubric = RUBRIC_PATH.read_text(encoding="utf-8")
    return run_batches(rubric, plan_review(repo, change, rubric), reviewer, model)


def save_next_state(
    repo: Path, name: str, state: GateState, change: PendingChange, verdict: Verdict
) -> GateState:
    updated = next_state(state, change.base_tree, change.tree, change.head, verdict)
    save_state(repo, name, updated)
    return updated


def block_reason(verdict: Verdict, state: GateState) -> str:
    lines = [
        f"The review gate ({verdict.model}, round {state.blocked_rounds}) found problems in your diff.",
        "Fix each one, then stop again. The next stop reviews the whole diff since the last approval.",
        *(f"- {finding.render()}" for finding in verdict.findings),
    ]
    if state.blocked_rounds >= ROUNDS_BEFORE_TIEBREAK:
        lines.append(f"The next round goes to the tie-break reviewer, {TIEBREAK_MODEL}.")
    return "\n".join(lines)


def give_up_message(verdict: Verdict, rounds: int) -> str:
    return "\n".join([
        f"The review gate ({verdict.model}) gave up after {rounds} blocked rounds, so this stop goes through unapproved.",
        "The next stop reviews the same diff again, from round 1.",
        *(f"- {finding.render()}" for finding in verdict.findings),
    ])


def review_tip(
    repo: Path, state: GateState, change: PendingChange, rubric: str, reviewer: Reviewer
) -> Block | GiveUp | None:
    review = run_batches(rubric, plan_review(repo, change, rubric), reviewer, model_for(state))
    if review.unreviewed is not None:
        return Block(unfinished_reason(review))
    updated = save_next_state(repo, HOOK_STATE_FILE, state, change, review.verdict)
    if review.verdict.passed:
        return None
    if updated.blocked_rounds >= MAX_BLOCKED_ROUNDS:
        save_state(repo, HOOK_STATE_FILE, replace(updated, blocked_rounds=0))
        return GiveUp(give_up_message(review.verdict, updated.blocked_rounds))
    return Block(block_reason(review.verdict, updated))


def hook_decision(repo: Path, event: StopEvent, reviewer: Reviewer) -> Outcome:
    if event.cwd.resolve() != repo.resolve():
        return None
    scope = strict_scope.load(repo)
    state = load_state(repo, HOOK_STATE_FILE)
    change = pending_change(repo, state, None)
    if not any(scope.contains(path) for path in change.paths):
        return None
    rubric = RUBRIC_PATH.read_text(encoding="utf-8")
    walk = walk_backlog(repo, scope, state, change, rubric, reviewer)
    if walk.block is not None:
        return with_skip_notices(walk.block, walk.skip_notices)
    if not any(scope.contains(path) for path in walk.change.paths):
        return with_skip_notices(None, walk.skip_notices)
    return with_skip_notices(review_tip(repo, walk.state, walk.change, rubric, reviewer), walk.skip_notices)


def review_from(repo: Path, base: str, reviewer: Reviewer) -> int:
    state = load_state(repo, BASE_STATE_FILE)
    change = pending_change(repo, state, base)
    if not change.paths:
        print(f"verdict: pass (nothing changed since {base})")
        return 0
    review = review_change(repo, change, reviewer, model_for(state))
    if review.unreviewed is not None:
        print(unfinished_reason(review))
        return 1
    verdict = review.verdict
    updated = save_next_state(repo, BASE_STATE_FILE, state, change, verdict)
    outcome = "pass" if verdict.passed else "block"
    print(f"verdict: {outcome} ({verdict.model}, {len(change.paths)} files since {base})")
    for finding in verdict.findings:
        print(f"- {finding.render()}")
    if not verdict.passed and updated.blocked_rounds >= ROUNDS_BEFORE_TIEBREAK:
        print(f"The next round goes to the tie-break reviewer, {TIEBREAK_MODEL}.")
    return 0 if verdict.passed else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--hook", action="store_true", help="run as the Claude Code Stop hook")
    mode.add_argument("--base", help="review the working tree against this revision")
    args = parser.parse_args(argv)
    if args.hook:
        event = parse_stop_event(sys.stdin.read())
        outcome = None if event is None else hook_decision(REPO, event, claude_reviewer(REPO))
        if outcome is not None:
            print(json.dumps(outcome.payload()))
        return 0
    return review_from(REPO, args.base, claude_reviewer(REPO))


if __name__ == "__main__":
    sys.exit(main())
