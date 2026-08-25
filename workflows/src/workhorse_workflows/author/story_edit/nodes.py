"""Resolve a story-level command into the binding intent handed to epic-edit."""
from __future__ import annotations

import logging
from pathlib import Path

from ostler import Ostler
from workhorse.pyflow import Blueprint, WorkflowFailed
from workhorse_workflows.author.main.nodes.stories import resolve_bullet
from workhorse_workflows.author.shared.schemas import EditIntent

blueprint = Blueprint("author-story-edit")


def _intent_stub(
    logger: logging.Logger,
    action: str,
    epic: str = "",
    story: str = "",
    bullet: str = "",
    reason: str = "",
    force: bool = False,
    backlog: str = "",
    epics_dir: str = "",
    repo_dir: str = "",
) -> EditIntent:
    return EditIntent(
        kind="remove-story" if action == "remove" else "add-story",
        epic=epic,
        story=story,
        bullet_id="dry-run-item",
        source_bullet=bullet,
        change=reason or "dry-run edit",
        force=force,
    )


@blueprint.node(stub=_intent_stub)
def resolve_story_intent(
    logger: logging.Logger,
    action: str,
    epic: str = "",
    story: str = "",
    bullet: str = "",
    reason: str = "",
    force: bool = False,
    backlog: str = "",
    epics_dir: str = "",
    repo_dir: str = "",
) -> EditIntent:
    """Validate the requested story operation and name its parent epic and binding outcome."""
    if action == "add":
        if not epic.strip() or not bullet.strip():
            raise WorkflowFailed("story-edit add needs both 'epic' and 'bullet'")
        resolved = resolve_bullet(Path(repo_dir), bullet, backlog)
        logger.info("resolved add-story intent for %s from %s", epic, resolved.id)
        return EditIntent(
            kind="add-story",
            epic=epic.strip(),
            bullet_id=resolved.id,
            source_bullet=resolved.source_bullet,
            from_backlog=resolved.from_backlog,
            change=reason.strip() or f"Add a story for {resolved.source_bullet}",
            force=force,
        )
    if action != "remove":
        raise WorkflowFailed("story-edit action must be 'add' or 'remove'")
    slug = story.strip()
    if not slug:
        raise WorkflowFailed("story-edit remove needs 'story'")
    row = next(
        (
            row
            for row in Ostler(
                repo_dir,
                doc_roots={"epics": epics_dir} if epics_dir else {},
            ).list("story")
            if str(row["slug"]) == slug
        ),
        None,
    )
    if row is None:
        raise WorkflowFailed(f"story '{slug}' does not exist")
    status = str(row["status"])
    if status.lower() != "not started" and not force:
        raise WorkflowFailed(
            f"story '{slug}' has status '{status or '<blank>'}' — refusing to delete; "
            "rerun with force=true if removing started work is intentional"
        )
    parent = str(row["epic"])
    logger.info("resolved remove-story intent for %s from %s", slug, parent)
    return EditIntent(
        kind="remove-story",
        epic=parent,
        story=slug,
        change=reason.strip() or f"Remove story {slug} and reconcile its epic scope",
        force=force,
    )


__all__ = ["blueprint", "resolve_story_intent"]
