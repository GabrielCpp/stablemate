"""What the epic's PR boundary decided: open it, gate on it, merge it, or escalate it.

Ported from the main graph's `open_pr` / `merge` / `flag_ci_fail` / `flag_merge_fail` nodes
and story mode's `open_story_pr`.

**Both tri-states are `Literal`s, and both are Python-produced, so both carry a default**
(`_base.py`). `merge_status` is `merged | unavailable | failed` and defaults to the
pessimistic arm: a merge nobody could report on must route the way a failed one does, and
`guard_merge` is where `failed` goes. `story_pr` is `opened | exists | skipped` and nothing
branches on it — its node's only successor is the terminal — but it stays three arms rather
than a bool because it is a *report*: "I opened one" and "one was already open" are the
whole of what it is read for.

`MergeFixResult.status` is the module's one **agent**-produced status, so it is required and
has no default. `should_gate` and the two `*_flagged` fields are the ordinary two-state case
and are bools.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from workhorse_workflows.coder.shared.schemas._base import CoderResult


class PrGate(CoderResult):
    """`open-pr.py` — the epic's PR is (or is not) something to gate CI on.

    `ci_epic` and `ci_base` are carried forward rather than re-derived: every later node in
    the CI/merge chain reads them from here, so the branch the gate polls and the branch the
    merge targets cannot drift from the ones the PR was opened against.
    """

    should_gate: bool = False
    ci_epic: str = ""
    ci_base: str = ""


class MergeOutcome(CoderResult):
    """`merge-pr.py` — `merged`, `unavailable` or `failed`, and the base it targeted.

    `unavailable` is the tolerated one: no token, no origin, a non-github remote, or no open
    PR. An offline run (a local bind-mount clone) passes straight through it and still
    advances the queue. `failed` is a merge that was **attempted** and did not land — a
    conflict, a branch behind base, branch protection — and it is the arm the blank joins.
    """

    merge_status: Literal["merged", "unavailable", "failed"] = "failed"
    base_branch: str = ""


class StoryPr(CoderResult):
    """`open-story-pr.py` — one PR per affected code repo, and the URLs that resulted.

    `story_pr` is the best result across the repos, not a per-repo verdict: `opened` if any
    repo got a new PR, else `exists` if any already had one, else `skipped`. `pr_urls`
    carries every PR that exists now, opened this run or not.
    """

    story_pr: Literal["opened", "exists", "skipped"] = "skipped"
    pr_urls: list[str] = []


class CiFlagged(CoderResult):
    """`flag-ci-failure.py` — did the give-up note reach the PR?

    False is not a failure: with no token, no reachable repo, or no open PR there is nothing
    to comment on. The operator escalation itself is the gate the flow routes to next; this
    is the courtesy note on the way there.
    """

    ci_flagged: bool = False


class MergeFlagged(CoderResult):
    """`flag-merge-failure.py` — the merge-side twin of `CiFlagged`, same reading."""

    merge_flagged: bool = False


class MergeFixResult(CoderResult):
    """`fix_merge`'s reply — the conflict resolution the agent turn wrote.

    The optimistic half is not branched on: the YAML declared `fix_merge_result` as an
    output key and then routed unconditionally to `push_merge`, because whether the
    resolution *worked* is settled by the push and the re-merge, not by the turn's own
    account of itself. `blocked` is, because it is the one claim the re-merge cannot
    settle — a resolver saying the choice between the two sides is not its to make — and
    the remaining reworks would each re-ask a turn that has already answered.
    """

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
