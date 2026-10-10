"""The CI fix loop's models: what the workspace holds, what CI says, what a push did."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from workhorse.pyflow import dry_run

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


@dry_run(status="fixed")
class FixCiResult(CoderResult):
    """`fix_ci/prompts/fix-ci.md`: the CI owner's report, `fixed`, `failed` or `blocked`."""

    status: Literal["fixed", "failed", "blocked"] = Field(
        description="`fixed`: you found the failure, repaired it, verified the failing job's "
        "commands locally and committed. `failed`: you understood the failure but this turn "
        "did not repair it, or it looks like infrastructure flake. Make no spurious commit. "
        "The workflow polls CI again and hands you the result. `blocked`: nothing you can do "
        "in this repository would make CI green, so another turn is the same turn. The checks "
        "are unreadable to this token, the fix needs a credential or a deployment you cannot "
        "perform, the failure lives in a repo you were not given, or CI can only go green by "
        "changing an observable contract, which this lane may not do because no story "
        "documentation context exists here. The workflow asks the level above you.",
    )
    notes: str = Field(
        default="",
        description="What you changed, or what you tried and why it did not work. On "
        "`blocked`, the specific dependency, what you attempted before concluding it, and "
        "the question whose answer would unblock you.",
    )


class CiLoop(BaseModel):
    """What one lap of the ship lane carries to the next: the repo, the repair turns, the misses, the merges."""

    repo: str = ""
    repo_dir: str = ""
    processed: list[str] = []
    laps: int = 0
    unread: list[str] = []
    merging: bool = False
    merges: int = 0


__all__ = [
    "CiChecks",
    "CiLoop",
    "CiRepoPick",
    "CiStatus",
    "FixCiResult",
    "PushOutcome",
    "WorkspaceDirs",
]
