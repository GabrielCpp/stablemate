"""What the epic's PR boundary decided: open it, gate on it, merge it, or escalate it.

Ported from the main graph's `open_pr` / `merge` / `flag_ci_fail` / `flag_merge_fail` nodes
and story mode's `open_story_pr`.

**One tri-state stays a string here, for the reason `schemas/ci.py` records.** `merge_status`
is `merged | unavailable | failed`, and `decide_merge`'s `default:` arm is `guard_merge` —
the *pessimistic* one — so a blank must route the way `failed` does. A pair of bools cannot
express that without inventing a third, so the port keeps the string and writes the branch
as `if status in (...)` with a comment naming the arm the blank falls into.

`story_pr` is a tri-state too (`opened | exists | skipped`) but nothing branches on it: its
node's only successor is the terminal. It stays a string because it is a *report*, not a
router — collapsing it to a bool would throw away the difference between "I opened one" and
"one was already open", which is the whole of what the field is read for.

`should_gate` and the two `*_flagged` fields are the ordinary two-state case and are bools:
each is `yes`/`no` in the YAML with a blank that means `no`, which is what a bool already is.
"""
from __future__ import annotations

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

    merge_status: str = ""
    base_branch: str = ""


class StoryPr(CoderResult):
    """`open-story-pr.py` — one PR per affected code repo, and the URLs that resulted.

    `story_pr` is the best result across the repos, not a per-repo verdict: `opened` if any
    repo got a new PR, else `exists` if any already had one, else `skipped`. `pr_urls`
    carries every PR that exists now, opened this run or not.
    """

    story_pr: str = "skipped"
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

    status: str = ""
    notes: str = ""


__all__ = [
    "CiFlagged",
    "MergeFixResult",
    "MergeFlagged",
    "MergeOutcome",
    "PrGate",
    "StoryPr",
]
