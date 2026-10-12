"""What the run's PR boundary decided: open it, merge it, or escalate it."""
from __future__ import annotations

from typing import Literal

from pydantic import Field
from workhorse.pyflow import dry_run

from workhorse_workflows.coder.shared.schemas._base import CoderResult


class RunPrs(CoderResult):
    """`open_run_prs` — one PR per repo the run branch changed, and the URLs that resulted."""

    status: Literal["opened", "skipped"] = "skipped"
    pr_urls: list[str] = []


class MergeOutcome(CoderResult):
    """`merge-pr.py` — `merged`, `unavailable` or `failed`, and the base it targeted."""

    merge_status: Literal["merged", "unavailable", "failed"] = "failed"
    base_branch: str = ""


class MergeFlagged(CoderResult):
    """`flag-merge-failure.py` — did the give-up note reach the PR?"""

    merge_flagged: bool = False


@dry_run(status="fixed")
class MergeFixResult(CoderResult):
    """`fix_ci/prompts/fix-merge.md`: the conflict resolution the ship lane's merge turn wrote."""

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
    "MergeFixResult",
    "MergeFlagged",
    "MergeOutcome",
    "RunPrs",
]
