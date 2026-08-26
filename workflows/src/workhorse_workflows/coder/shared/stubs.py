"""What the coder's gates return under `--dry-run`.

A dry run replaces every node body with a stand-in, and an undeclared stand-in is a
**blank** instance of the return model. For genesis that reads `ok=False` at every step,
which is not a neutral default: the classifier's `ok=False` is a `raise WorkflowFailed`,
and the validator's `valid=False` is the repair loop, which spends its two reworks on
nothing and then fails the run. A dry run is meant to walk the happy path and prove the
graph is wired; ending it in the error arm proves only that the error arm exists.

So the four gates genesis branches on are declared here. The one that is *not* declared
is as deliberate as the ones that are:

* `select_ci_repo` — blank means `has_repo=False`, which ends the CI loop on its first
  pass. Stubbing it truthy would send a dry run round a poll/fix cycle that has no PR to
  poll and no agent to fix with.
The same argument covers the story spine. `prepare_story` blank means `story_path == ""`,
and `docs` (and every other per-story flow that resolves the slug for itself) raises
`WorkflowFailed` on exactly that, because a slug that would not resolve is a run with
nothing to work on. A dry run would stop at the first `handoff` past `dev` and never reach
the QA/commit/PR cluster at the far end — the half of the graph a smoke test is most for.
"""
from __future__ import annotations

from workhorse_workflows.coder.shared.schemas.genesis import (
    FarrierInstall,
    GenesisReport,
    Skeleton,
    TargetClassification,
)
from workhorse_workflows.coder.shared.schemas.story import StoryPaths

#: The synthetic story a dry run walks. Named so it is unmistakable in `events.jsonl`,
#: and rooted somewhere that plainly does not exist — nothing under `--dry-run` opens it.
_SLUG = "dry-run-story"
_EPIC = "dry-run-epic"
_DIR = f"/dry-run/docs/epics/{_EPIC}/stories/{_SLUG}"


def classified(*_args: object, **_kwargs: object) -> TargetClassification:
    """`resolve_genesis_target` — a target worth running genesis on.

    `target_state="absent"` on purpose: it is the arm that visits every subsequent state,
    which is what a dry run is for.
    """
    return TargetClassification(ok=True, note="dry run")


def built(*_args: object, **_kwargs: object) -> Skeleton:
    """`init_skeleton` — the stack's init command ran and left its marker."""
    return Skeleton(ok=True, note="dry run")


def installed(*_args: object, **_kwargs: object) -> FarrierInstall:
    """`install_farrier` — adapters rendered and every scaffold took."""
    return FarrierInstall(ok=True, note="dry run")


def valid(*_args: object, **_kwargs: object) -> GenesisReport:
    """`validate_genesis` — the repo satisfies every precondition the main loop assumes."""
    return GenesisReport(valid=True)


def story_paths(*_args: object, **_kwargs: object) -> StoryPaths:
    """`prepare_story` — a slug that resolved, so the per-story flows have work to do."""
    return StoryPaths(
        story_path=f"{_DIR}/story.md",
        spec_dir=f"{_DIR}/spec",
        qa_dir=f"{_DIR}/qa",
        story_slug=_SLUG,
        story_epic=_EPIC,
    )


__all__ = ["built", "classified", "installed", "story_paths", "valid"]
