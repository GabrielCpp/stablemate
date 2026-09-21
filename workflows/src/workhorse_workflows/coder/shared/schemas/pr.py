"""What the epic's PR boundary decided: open it, gate on it, merge it, or escalate it."""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from workhorse_workflows.coder.shared.schemas._base import CoderResult


class PrGate(CoderResult):
    """`open-pr.py` — the epic's PR is (or is not) something to gate CI on."""

    should_gate: bool = False
    ci_epic: str = ""
    ci_base: str = ""


class MergeOutcome(CoderResult):
    """`merge-pr.py` — `merged`, `unavailable` or `failed`, and the base it targeted."""

    merge_status: Literal["merged", "unavailable", "failed"] = "failed"
    base_branch: str = ""


class StoryPr(CoderResult):
    """`open-story-pr.py` — one PR per affected code repo, and the URLs that resulted."""

    story_pr: Literal["opened", "exists", "skipped"] = "skipped"
    pr_urls: list[str] = []


class CiFlagged(CoderResult):
    """`flag-ci-failure.py` — did the give-up note reach the PR?"""

    ci_flagged: bool = False


class MergeFlagged(CoderResult):
    """`flag-merge-failure.py` — the merge-side twin of `CiFlagged`, same reading."""

    merge_flagged: bool = False


class MergeFixResult(CoderResult):
    """`fix_merge`'s reply — the conflict resolution the agent turn wrote."""

    status: Literal["fixed", "failed", "blocked"] = Field(
        description="`fixed` — the branches merge cleanly now and the resolution is "
        "committed. `failed` — this attempt did not finish the resolution, but another one "
        "on the same two branches plausibly would. `blocked` — no attempt of this stage can "
        "resolve it: both sides of a conflict are deliberate and choosing between them is a "
        "product decision present in neither branch, the divergence is a history rewrite "
        "rather than a content conflict, or resolving it needs work in a repo you were not "
        "given. Resolving a conflict wrongly corrupts code silently rather than failing "
        "loudly, so hand it to an operator instead of guessing.",
    )
    notes: str = Field(
        default="",
        description="What you resolved — a content merge, or stale-duplicate remediation; "
        "say which. On `blocked`, exactly which files and which decision you could not make, "
        "and what you attempted first.",
    )


__all__ = [
    "CiFlagged",
    "MergeFixResult",
    "MergeFlagged",
    "MergeOutcome",
    "PrGate",
    "StoryPr",
]
