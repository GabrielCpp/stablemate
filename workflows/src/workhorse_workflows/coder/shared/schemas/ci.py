"""The CI fix loop's models: what the workspace holds, what CI says, what a push did.

Ported from the `fix_ci` flow's five script nodes and its one agent turn.

**Two tri-states stay strings here, and that is a deliberate divergence from `author`.**
`author` split every tri-state into bools (`verify_ok: "skip"` became `holds` plus
`nothing_surveyed`), because each of its tri-states had a clean two-bit reading. These do
not: `ci_status` is `passed | failed | unavailable` and `push_status` is
`pushed | unavailable | failed`, and in both cases the YAML's `default:` arm — the one a
blank value takes — is the *pessimistic* one:

* `decide_ci` routes `passed` and `unavailable` onward to the next repo, and everything
  else, `default:` included, into the attempts guard and the fixer;
* `decide_push_fix` routes `pushed` and `unavailable` back to the poll, and everything
  else, `default:` included, to the terminal.

A pair of bools cannot express "the blank takes the third arm" without inventing a third
bool, so the port keeps the string and writes the branch as `if status in (...)`. Every
such branch names the arm the blank falls into, in a comment at the site.

The `processed_repos` accumulator is the one place a JSON-encoded **string** becomes a real
`list[str]`. The YAML round-tripped it through `json.dumps`/`json.loads` on every hop
because a workflow var is a string; a state parameter is a value, so the encoding has no
job left to do. Nothing on disk carried the encoded form.

`WorkspaceDirs` lived here while `fix_ci` was the only flow that had one; it is defined in
`schemas/story.py` now, because `resolve-workspace-dirs.py` is the story spine's and every
per-story flow returns it. It stays importable from here — `fix_ci` is still a caller.
"""
from __future__ import annotations

from workhorse_workflows.coder.shared.schemas._base import CoderResult
from workhorse_workflows.coder.shared.schemas.story import WorkspaceDirs


class CiRepoPick(CoderResult):
    """`select-ci-fix-repo.py` — which repo's CI to look at next, if any.

    `processed` is the accumulator that makes the loop terminate: a repo is appended the
    moment it is picked, so the next pass skips it whatever its CI did.
    """

    has_repo: bool = False
    repo: str = ""
    repo_cwd: str = ""
    processed: list[str] = []


class CiChecks(CoderResult):
    """`await-pr-checks.py` — the settled verdict of one PR's Actions runs.

    `status` is `passed`, `failed` or `unavailable`; see the module docstring for why it
    is a string. `summary` is what the fixer agent is handed as its brief, so it carries
    the failing run names rather than a count wherever the API gave them up.
    """

    status: str = ""
    summary: str = ""


class PushOutcome(CoderResult):
    """`push-ci.py` — `pushed`, `unavailable` or `failed`, and why.

    `unavailable` is the tolerated one (no branch, no token, no github origin: an offline
    run still completes). `failed` means a push was attempted and did not land, or landed
    without the remote head advancing — which is precisely what let the fix loop spin
    against an unmoved PR head until its attempts ran out.
    """

    status: str = ""
    notes: str = ""


class FixCiResult(CoderResult):
    """`fix_ci/prompts/fix-ci.md` — the fixer's own report: `fixed`, `failed` or `blocked`.

    The optimistic half is not branched on: the push and the next poll decide whether the
    fix worked, and an agent claiming `fixed` is not evidence that it did. `blocked` is,
    for the reason the whole asymmetry exists — a fixer saying nothing in this repository
    would make the checks green is the one claim the next poll cannot check, and spending
    the remaining attempts on it just re-asks a turn that has already answered.
    """

    status: str = ""
    notes: str = ""


__all__ = ["CiChecks", "CiRepoPick", "FixCiResult", "PushOutcome", "WorkspaceDirs"]
