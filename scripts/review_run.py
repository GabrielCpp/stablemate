"""One review of a change: the batches its diff is cut into, the model that reads them, and what the stop hook answers with."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from review_diff import CHARS_PER_TOKEN, ReviewBatches, pack, split_diff
from review_git import git
from review_state import GateState
from review_verdict import Reviewer, ReviewError, Verdict

PRIMARY_MODEL = "claude-sonnet-5"
TIEBREAK_MODEL = "claude-opus-5-5"
ROUNDS_BEFORE_TIEBREAK = 2
PROMPT_BUDGET_TOKENS = 60_000
MAX_BATCHES = 4


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
class Notice:
    message: str

    def payload(self) -> dict[str, str]:
        return {"systemMessage": self.message}


type Outcome = Block | GiveUp | Notice | None


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


def unfinished_reason(review: BatchedVerdict) -> str:
    found = [f"- {finding.render()}" for finding in review.verdict.findings]
    return "\n".join([
        f"The review gate ({review.verdict.model}) failed on {review.unreviewed},"
        " so your diff is not approved and this round does not count.",
        "Fix what the finished batches found, then stop again to review the whole diff."
        if found else "Stop again to review the whole diff.",
        *found,
    ])
