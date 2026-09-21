"""The review flow's models: two review turns, the settlement gate, the feedback inbox."""
from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, Field

from workhorse_workflows.coder.shared.schemas._base import CoderResult, Finding

ReviewCategory = Literal["Bug", "Standard", "Reuse"]

CodeReviewStatus = Literal["findings", "clean", "skipped", "blocked"]

ReviewStatus = Literal["approved", "needs_changes", "blocked"]


class ReviewFinding(Finding):
    """A code-review finding: the base contract, plus which lens caught it and how sure it is."""

    category: ReviewCategory = Field(
        description="Which lens caught it. `Reuse` covers both duplicated code and a missed "
        "utility; the implementation reviewer selects on it to report those separately.",
    )

    score: int = Field(
        default=0,
        description="The 0-100 confidence you scored it. Report every finding you scored, "
        "whatever it scored: the flow splits the list on this number, so a low score demotes "
        "a finding to advisory context, while one you drop yourself reaches nobody.",
    )


class CodeReviewResult(CoderResult):
    """`review/prompts/code-review.md` — the mechanical review pass over the diff."""

    status: CodeReviewStatus = Field(
        description="`findings` — the review found at least one issue in one or more repos. "
        "`clean` — it ran on at least one repo with local changes and found nothing. "
        "`skipped` — no affected repo had any local changes to review. `blocked` — the diff "
        "could not be read at all: the repos you were given are not the ones the change "
        "landed in, or the working tree is in a state (an unresolved conflict, a detached or "
        "missing branch) that no review of it would mean anything. `clean` and `blocked` are "
        "not the same answer — one says the diff is fine, the other that there was no diff "
        "to judge.",
    )
    findings: list[ReviewFinding] = Field(
        default=[], description="Empty for every status but `findings`."
    )
    findings_summary: str = Field(
        default="",
        description="One sentence on what was flagged — or what stopped you, on `blocked`.",
    )


class ReviewVerdict(CoderResult):
    """`review/prompts/review-implementation.md` — the binding verdict on the implementation."""

    status: ReviewStatus = Field(
        description="`approved` — no Critical or Major findings from either review pass. "
        "`needs_changes` — one or more require a fix before QA. `blocked` — you cannot reach "
        "either verdict, because what is missing is outside this repository: the change "
        "lives in a repo you were not given, judging it needs a product decision present in "
        "neither the story nor the plan, or the working tree holds no diff that corresponds "
        "to the story at all. An unwelcome verdict is not a blocked one — `needs_changes` "
        "exists to carry it, and reaching for `blocked` to avoid picking one takes the "
        "decision away from the only stage allowed to make it.",
    )
    notes: str = Field(
        default="",
        description="A brief summary of the findings from every review pass — the brief the "
        "repair turn is handed, so each finding names where it is and what must change. On "
        "`blocked`, the specific dependency and what you attempted before concluding it.",
    )


class ReviewContext(CoderResult):
    """`resolve-review-context.py` — where the review turns run, and what they may read."""

    docs_repo_path: str = ""
    affected_repo_paths: list[str] = []


class Feedback(CoderResult):
    """`check_feedback` — an un-consumed operator note dropped into the run's inbox."""

    present: bool = False
    content: str = ""


class ReviewLoop(BaseModel):
    """The three budgets one review round carries, as one state parameter rather than three."""

    rework: int = 0

    blocks: int = 0

    session_turns: int = 0

    COUNT_LABELS: ClassVar[tuple[str, ...]] = ("rework", "blocks", "session_turns")


class ReviewResult(CoderResult):
    """What the review flow hands back."""

    notes: str = ""


__all__ = [
    "CodeReviewResult",
    "CodeReviewStatus",
    "Feedback",
    "ReviewCategory",
    "ReviewContext",
    "ReviewFinding",
    "ReviewLoop",
    "ReviewResult",
    "ReviewStatus",
    "ReviewVerdict",
]
