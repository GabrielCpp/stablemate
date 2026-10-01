"""The operator's notes on the story being written."""
from __future__ import annotations

import logging

from workhorse_workflows.author.shared.schemas.main import Feedback
from workhorse_workflows.author.story_author.nodes._blueprint import blueprint
from workhorse_workflows.kit import poll_run_inbox


@blueprint.node
def check_story_feedback(logger: logging.Logger, run_dir: str = "") -> Feedback:
    """Poll the operator's run-scoped inbox for un-consumed feedback."""
    polled = poll_run_inbox(run_dir, reply_text="folded into a story rework")
    if polled is None:
        logger.info("no outstanding inbox messages")
        return Feedback()
    content, scope = polled
    logger.info("feedback present (scope=%s)", scope)
    return Feedback(present=True, scope=scope, content=content)


__all__ = ["check_story_feedback"]
