"""Resolve and migrate the one story the caller explicitly requested."""
from __future__ import annotations

import logging
import hashlib
import json
from pathlib import Path

from ostler import Ostler
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.author.shared.paths import survey_repo_root
from workhorse_workflows.author.story_author.nodes._blueprint import blueprint
from workhorse_workflows.author.story_author.schemas import AuditReceipt, StoryTarget


def _relative(root: Path, value: str | Path) -> str:
    path = Path(value)
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


@blueprint.node
def migrate_story(
    logger: logging.Logger,
    epic: str = "",
    story: str = "",
    epics_dir: str = "",
    repo_dir: str = "",
) -> StoryTarget:
    """Resolve exactly ``epic/story`` and migrate that story to the current shape."""
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

    result = okf.migrate_story_to_current_shape(story)
    if not result.ok:
        raise WorkflowFailed(result.message or f"could not migrate story '{story}'")

    story_path = _relative(root, str(row.get("path", "")))
    if not story_path:
        raise WorkflowFailed(f"story '{story}' in epic '{epic}' has no story.md path")
    story_dir = str(Path(story_path).parent)
    try:
        epic_dir = _relative(root, okf.epic_dir(epic))
    except (OSError, ValueError, RuntimeError) as exc:
        raise WorkflowFailed(f"could not resolve directory for epic '{epic}': {exc}") from exc

    configured = epics_dir.strip().rstrip("/")
    if configured and not Path(epic_dir).is_relative_to(Path(configured)):
        raise WorkflowFailed(
            f"epic '{epic}' resolved outside configured epics_dir '{configured}': {epic_dir}"
        )
    logger.info("prepared explicit story '%s' in epic '%s': %s", story, epic, result.message)
    return StoryTarget(
        epic=epic,
        story=story,
        epic_dir=epic_dir,
        story_dir=story_dir,
        story_path=story_path,
        migrated=True,
        migration_message=result.message,
    )


@blueprint.node
def record_story_audit(
    logger: logging.Logger,
    story_path: str,
    repo_dir: str = "",
) -> AuditReceipt:
    """Record a passing audit against the exact story bytes it judged."""
    root = survey_repo_root(repo_dir)
    path = root / story_path
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    receipt = path.parent / "audit-receipt.json"
    receipt.write_text(
        json.dumps({"status": "passed", "storyDigest": digest}, indent=2) + "\n",
        encoding="utf-8",
    )
    relative = receipt.relative_to(root).as_posix()
    logger.info("recorded passing story audit at %s", relative)
    return AuditReceipt(story_digest=digest, path=relative)


__all__ = ["migrate_story", "record_story_audit"]
