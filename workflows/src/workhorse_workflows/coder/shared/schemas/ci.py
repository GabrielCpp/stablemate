"""The CI fix loop's models: what the workspace holds, what CI says, what a push did.

Every status here is a `Literal`, typed by who produces it — the rule and its reasoning
live in `_base.py`. `CiChecks` and `PushOutcome` are read off the GitHub API by Python, so
each keeps a default, and the default is the pessimistic arm a blank value used to take:
`failed` in both cases. `FixCiResult` is the fixer agent's own report, so its status is
required — a turn that will not say what it did is a parse failure and gets re-asked.

**"Cannot look" and "there is nothing to look at" are different answers.** `unavailable`
is the second one: no branch, no origin, no open PR, no Actions runs — facts about a repo
that has no CI, which the loop proceeds past because an offline or CI-less run completing
is the point. `blocked` is the first: the API was reachable and refused, or answered and
could not be understood. That used to be `unavailable` too, and a token missing
`Actions:Read` therefore read as a green gate on every repo in the workspace. It escalates
now, and `unavailable` is named in the loop's closing summary rather than passing silently.

`CiLoop` is the loop's own carriage rather than any node's return; see its docstring.

The `processed` accumulator is the one place a JSON-encoded **string** became a real
`list[str]`. The YAML round-tripped it through `json.dumps`/`json.loads` on every hop
because a workflow var is a string; a state parameter is a value, so the encoding has no
job left to do.

`WorkspaceDirs` is defined in `schemas/story.py` — `resolve-workspace-dirs.py` is the story
spine's and every per-story flow returns it. It stays importable from here, because
`fix_ci` is still a caller.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from workhorse_workflows.coder.shared.schemas._base import CoderResult
from workhorse_workflows.coder.shared.schemas.story import WorkspaceDirs


#: What a poll can conclude. Named because a caller that stands in for `poll_pr_checks`
#: — the main graph's tests do — has to spell the same closed set, and a second literal is
#: a second set the moment an arm is added here.
type CiStatus = Literal["passed", "failed", "unavailable", "blocked"]


class CiRepoPick(CoderResult):
    """`select_ci_repo` — which repo's CI to look at next, if any.

    `processed` is the accumulator that makes the loop terminate: a repo is appended the
    moment it is picked, so the next pass skips it whatever its CI did.
    """

    has_repo: bool = False
    repo: str = ""
    repo_cwd: str = ""
    processed: list[str] = []


class CiChecks(CoderResult):
    """`poll_pr_checks` — the settled verdict of one PR's Actions runs.

    `summary` is what the fixer agent is handed as its brief, so it carries the failing run
    names and their run ids rather than a count wherever the API gave them up — and on
    `unavailable` and `blocked` it carries the reason, which is what lets the loop's
    closing line say which repos were never actually gated.
    """

    status: CiStatus = "failed"
    summary: str = ""


class PushOutcome(CoderResult):
    """`push_ci_fix` — `pushed`, `unavailable` or `failed`, and why.

    `unavailable` is the tolerated one (no branch, no token, no github origin: an offline
    run still completes). `failed` means a push was attempted and did not land, or landed
    without the remote head advancing — which is precisely what let the fix loop spin
    against an unmoved PR head until its attempts ran out.
    """

    status: Literal["pushed", "unavailable", "failed"] = "failed"
    notes: str = ""


class FixCiResult(CoderResult):
    """`fix_ci/prompts/fix-ci.md` — the fixer's own report: `fixed`, `failed` or `blocked`.

    The optimistic half is not branched on: the push and the next poll decide whether the
    fix worked, and an agent claiming `fixed` is not evidence that it did. `blocked` is,
    for the reason the whole asymmetry exists — a fixer saying nothing in this repository
    would make the checks green is the one claim the next poll cannot check, and spending
    the remaining attempts on it just re-asks a turn that has already answered.
    """

    status: Literal["fixed", "failed", "blocked"] = Field(
        description="`fixed` — you found the failure, repaired it, verified the gate locally "
        "and committed. `failed` — you understood the failure but this attempt did not "
        "repair it, or it looks like infrastructure flake; make no spurious commit, and the "
        "workflow retries. `blocked` — nothing you can do in this repository would make CI "
        "green, so another attempt is the same attempt: the checks are unreadable to this "
        "token, the fix needs a credential or a deployment you cannot perform, the failure "
        "lives in a repo you were not given, or CI can only be made green by changing an "
        "observable contract, which this stage may not do because no story documentation "
        "context exists here.",
    )
    notes: str = Field(
        default="",
        description="What you changed, or what you tried and why it did not work. On "
        "`blocked`, the specific dependency and what you attempted before concluding it.",
    )


class CiLoop(BaseModel):
    """What one lap of the CI loop carries to the next: the repo, the tally, the misses.

    Four parameters travelled the four states together, in the same order, doing nothing
    apart — the shape that turns a new piece of loop state into an edit at every arrow.
    They are one value here, and a state signature says `loop: CiLoop`.

    Not a `CoderResult`: nothing returns it and no agent fills it in, so it wants neither
    the dropped nulls nor the `blocked` reading. It is checkpointed like any state
    parameter and revived through the annotation on the state that declares it.

    `attempts` is a **lifetime** budget across every repo, not a per-repo one: the loop
    never resets it when `start` advances, so the second repo inherits whatever the first
    spent. That is the pinned behaviour — the YAML's comment claimed per-repo and its
    counter never reset either.
    """

    #: The workspace key of the repo this lap is gating.
    repo: str = ""
    #: That repo's checkout. Every node takes it as an argument; nothing reads a cwd.
    repo_dir: str = ""
    #: Repos already picked, whatever their CI did. What makes the outer loop terminate.
    processed: list[str] = []
    #: `fix → push → poll` cycles spent so far, across every repo.
    attempts: int = 0
    #: `<repo>: <reason>` for each repo whose CI could not be gated at all, so the run's
    #: closing line can name them. An unread gate is not a passed gate.
    unread: list[str] = []


__all__ = [
    "CiChecks",
    "CiLoop",
    "CiRepoPick",
    "CiStatus",
    "FixCiResult",
    "PushOutcome",
    "WorkspaceDirs",
]
