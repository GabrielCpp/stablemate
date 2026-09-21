"""What the coder's gates return under `--dry-run`."""
from __future__ import annotations

from workhorse_workflows.coder.shared.schemas.genesis import (
    FarrierInstall,
    GenesisReport,
    Skeleton,
    TargetClassification,
)
from workhorse_workflows.coder.shared.schemas.story import StoryPaths

_SLUG = "dry-run-story"
_EPIC = "dry-run-epic"
_DIR = f"/dry-run/docs/epics/{_EPIC}/stories/{_SLUG}"


def classified(*_args: object, **_kwargs: object) -> TargetClassification:
    """`resolve_genesis_target` — a target worth running genesis on."""
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
