"""A story's status and the operator's answer file."""
from __future__ import annotations

import logging

from workhorse import gates
from workhorse_workflows.kit import find_docs_root
from workhorse_workflows.coder.shared import paths
from workhorse_workflows.coder.shared import story_status
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.dev import (
    OperatorAnswer,
    StoryStatusCheck,
)
from ostler.select import is_done

AWAITING = "AWAITING_OPERATOR"
ANSWERED = "ANSWERED"
CONSUMED = "CONSUMED"


@blueprint.node
def check_story_status(
    logger: logging.Logger,
    docs_path: str = "",
    slug: str = "",
    epic: str = "",
    story_path: str = "",
    repo_dir: str = "",
) -> StoryStatusCheck:
    """Whether the turn just taken stamped the story finished."""
    root = find_docs_root(docs_path, repo_dir)
    written = story_status.current(root, slug, epic=epic, story_path=story_path).strip()
    if not is_done(written):
        return StoryStatusCheck(status="clean", written=written)
    logger.warning(
        "the story's Status reads %r, which marks it finished, before QA has run", written
    )
    return StoryStatusCheck(status="dirty", written=written)


@blueprint.node
def read_operator_context(logger: logging.Logger, story_path: str = "") -> OperatorAnswer:
    """Take the operator's answer off `<story-folder>/context.md` and consume it."""
    ctx = paths.story_context_path(story_path)
    if not ctx.exists():
        logger.warning("no operator context at %s — treating the block as unanswered", ctx)
        return OperatorAnswer()

    content = ctx.read_text(encoding="utf-8")
    if gates.status_of(content) == ANSWERED:
        ctx.write_text(gates.set_status(content, CONSUMED), encoding="utf-8")
        logger.info("consumed the operator's answer in %s", ctx)

    scope = "epic" if gates.scope_of(content) == "epic" else "story"
    return OperatorAnswer(answered=True, scope=scope, content=content)


__all__ = [
    "check_story_status",
    "read_operator_context",
]
