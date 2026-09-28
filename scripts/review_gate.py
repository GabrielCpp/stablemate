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
from review_diff import CHARS_PER_TOKEN, ReviewBatches, pack, split_diff
from review_git import first_parent_commits, git, is_ancestor, snapshot_tree, tree_exists
from review_state import BASE_STATE_FILE, HOOK_STATE_FILE, GateState, load_state, next_state, save_state
from review_verdict import Reviewer, ReviewError, Verdict

REPO = Path(__file__).resolve().parents[1]
RUBRIC_PATH = Path(__file__).resolve().with_name("review_gate_prompt.md")
PRIMARY_MODEL = "claude-sonnet-5"
TIEBREAK_MODEL = "claude-opus-5-5"
ROUNDS_BEFORE_TIEBREAK = 2
PROMPT_BUDGET_TOKENS = 60_000
MAX_BATCHES = 4
MAX_BLOCKED_ROUNDS = 10


@dataclass(frozen=True)
class PendingChange:
    head: str
    base_tree: str
    tree: str
    paths: tuple[str, ...]


@dataclass(frozen=True)
class Block:
    reason: str

    def payload(self) -> dict[str, str]:
        return {"decision": "block", "reason": self.reason}


@dataclass(frozen=True)
class GiveUp:
    message: str

    def payload(self) -> dict[str, str]:
        return {"systemMessage": self.message}


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


def model_for(state: GateState) -> str:
    if state.blocked_rounds >= ROUNDS_BEFORE_TIEBREAK:
        return TIEBREAK_MODEL
    return PRIMARY_MODEL


@dataclass(frozen=True)
class BatchedVerdict:
    verdict: Verdict
    unreviewed: str | None


def plan_review(repo: Path, change: PendingChange, rubric: str) -> ReviewBatches:
    diff = git(repo, "diff", "--no-color", "-M", "-D", change.base_tree, change.tree)
    budget_tokens = PROMPT_BUDGET_TOKENS - len(rubric) // CHARS_PER_TOKEN
    return pack(split_diff(diff), budget_tokens, MAX_BATCHES)


def run_batches(rubric: str, plan: ReviewBatches, reviewer: Reviewer, model: str) -> BatchedVerdict:
    findings = list(plan.too_large)
    for done, batch in enumerate(plan.batches):
        try:
            findings.extend(reviewer(rubric + batch, model).findings)
        except ReviewError as exc:
            unreviewed = f"batch {done + 1} of {len(plan.batches)}: {exc}"
            return BatchedVerdict(verdict=Verdict(model=model, findings=tuple(findings)), unreviewed=unreviewed)
    return BatchedVerdict(verdict=Verdict(model=model, findings=tuple(findings)), unreviewed=None)


def review_change(repo: Path, change: PendingChange, reviewer: Reviewer, model: str) -> BatchedVerdict:
    rubric = RUBRIC_PATH.read_text(encoding="utf-8")
    return run_batches(rubric, plan_review(repo, change, rubric), reviewer, model)


def unfinished_reason(review: BatchedVerdict) -> str:
    found = [f"- {finding.render()}" for finding in review.verdict.findings]
    return "\n".join([
        f"The review gate ({review.verdict.model}) failed on {review.unreviewed},"
        " so your diff is not approved and this round does not count.",
        "Fix what the finished batches found, then stop again to review the whole diff."
        if found else "Stop again to review the whole diff.",
        *found,
    ])


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


@dataclass(frozen=True)
class RangeStep:
    state: GateState
    skipped: str | None
    block: Block | None


def in_backlog(repo: Path, state: GateState, change: PendingChange) -> bool:
    return (
        state.base_head is not None
        and state.base_tree == change.base_tree
        and state.base_head != change.head
        and is_ancestor(repo, state.base_head, change.head)
    )


def commit_change(repo: Path, base_tree: str, commit: str) -> PendingChange:
    tree = git(repo, "rev-parse", f"{commit}^{{tree}}")
    names = git(repo, "diff", "--name-only", base_tree, tree)
    return PendingChange(head=commit, base_tree=base_tree, tree=tree, paths=tuple(names.splitlines()))


def widest_range(repo: Path, base_tree: str, commits: list[str], rubric: str) -> PendingChange | None:
    fitting = None
    for commit in commits:
        candidate = commit_change(repo, base_tree, commit)
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
        alone = commit_change(repo, change.base_tree, commits[0])
        skipped = f"Commit {commits[0][:8]} is too large to review on its own, so it goes through unreviewed."
        return RangeStep(GateState(alone.tree, alone.head, 0), skipped, None)
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


def with_skipped(outcome: Block | GiveUp | None, skipped: list[str]) -> Block | GiveUp | None:
    if not skipped:
        return outcome
    if isinstance(outcome, Block):
        return Block("\n".join([*skipped, outcome.reason]))
    if isinstance(outcome, GiveUp):
        return GiveUp("\n".join([*skipped, outcome.message]))
    return GiveUp("\n".join(skipped))


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


def hook_decision(repo: Path, event: StopEvent, reviewer: Reviewer) -> Block | GiveUp | None:
    if event.cwd.resolve() != repo.resolve():
        return None
    scope = strict_scope.load(repo)
    state = load_state(repo, HOOK_STATE_FILE)
    change = pending_change(repo, state, None)
    if not any(scope.contains(path) for path in change.paths):
        return None
    rubric = RUBRIC_PATH.read_text(encoding="utf-8")
    skipped: list[str] = []
    while in_backlog(repo, state, change) and plan_review(repo, change, rubric).too_large:
        step = review_next_range(repo, scope, state, change, rubric, reviewer)
        save_state(repo, HOOK_STATE_FILE, step.state)
        if step.skipped is not None:
            skipped.append(step.skipped)
        if step.block is not None:
            return with_skipped(step.block, skipped)
        state = step.state
        change = pending_change(repo, state, None)
    if not any(scope.contains(path) for path in change.paths):
        return with_skipped(None, skipped)
    return with_skipped(review_tip(repo, state, change, rubric, reviewer), skipped)


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
