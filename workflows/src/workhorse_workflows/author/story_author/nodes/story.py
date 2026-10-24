"""Resolve the one story the caller explicitly requested, and complete its scaffold."""
from __future__ import annotations

import logging
from pathlib import Path

from ostler import Ostler
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.author.shared.paths import survey_repo_root
from workhorse_workflows.author.story_author.nodes._blueprint import blueprint
from workhorse_workflows.author.story_author.schemas import StoryTarget


def _relative(root: Path, value: str | Path) -> str:
    path = Path(value)
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


@blueprint.node
def prepare_story(
    logger: logging.Logger,
    epic: str = "",
    story: str = "",
    repo_dir: str = "",
) -> StoryTarget:
    """Resolve exactly ``epic/story`` and give its document every required section it lacks."""
    epic = epic.strip()
    story = story.strip()
    if not epic or not story:
        raise WorkflowFailed("story-author requires explicit non-empty 'epic' and 'story' inputs")

    root = survey_repo_root(repo_dir)
    okf = Ostler(root)
    try:
        rows = okf.list("story", epic=epic)
    except (OSError, ValueError, RuntimeError) as exc:
        raise WorkflowFailed(f"could not resolve epic '{epic}': {exc}") from exc
    row = next((item for item in rows if str(item.get("slug", "")).strip() == story), None)
    if row is None:
        raise WorkflowFailed(f"story '{story}' was not found in epic '{epic}'")

    story_id = str(row.get("id", "") or "")
    if not story_id:
        raise WorkflowFailed(f"story '{story}' in epic '{epic}' has no id; give it an `id:` first")

    result = okf.scaffold_missing_sections(story_id)
    if not result.ok:
        raise WorkflowFailed(
            result.message or f"could not complete the scaffold for story '{story}'"
        )

    story_path = _relative(root, str(row.get("path", "")))
    if not story_path:
        raise WorkflowFailed(f"story '{story}' in epic '{epic}' has no story.md path")
    story_dir = str(Path(story_path).parent)
    try:
        epic_dir = _relative(root, okf.epic_dir(epic))
    except (OSError, ValueError, RuntimeError) as exc:
        raise WorkflowFailed(f"could not resolve directory for epic '{epic}': {exc}") from exc

    logger.info("prepared explicit story '%s' in epic '%s': %s", story, epic, result.message)
    return StoryTarget(
        epic=epic,
        story=story,
        story_id=story_id,
        epic_dir=epic_dir,
        story_dir=story_dir,
        story_path=story_path,
        scaffolded=True,
        scaffold_message=result.message,
    )


__all__ = ["prepare_story"]
