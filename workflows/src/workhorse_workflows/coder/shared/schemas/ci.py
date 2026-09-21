"""The CI fix loop's models: what the workspace holds, what CI says, what a push did."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from workhorse_workflows.coder.shared.schemas._base import CoderResult
from workhorse_workflows.coder.shared.schemas.story import WorkspaceDirs


type CiStatus = Literal["passed", "failed", "unavailable", "blocked"]


class CiRepoPick(CoderResult):
    """`select_ci_repo` — which repo's CI to look at next, if any."""

    has_repo: bool = False
    repo: str = ""
    repo_cwd: str = ""
    processed: list[str] = []


class CiChecks(CoderResult):
    """`poll_pr_checks` — the settled verdict of one PR's Actions runs."""

    status: CiStatus = "failed"
    summary: str = ""


class PushOutcome(CoderResult):
    """`push_ci_fix` — `pushed`, `unavailable` or `failed`, and why."""

    status: Literal["pushed", "unavailable", "failed"] = "failed"
    notes: str = ""


class FixCiResult(CoderResult):
    """`fix_ci/prompts/fix-ci.md` — the fixer's own report: `fixed`, `failed` or `blocked`."""

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
    """What one lap of the CI loop carries to the next: the repo, the tally, the misses."""

    repo: str = ""
    repo_dir: str = ""
    processed: list[str] = []
    attempts: int = 0
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
