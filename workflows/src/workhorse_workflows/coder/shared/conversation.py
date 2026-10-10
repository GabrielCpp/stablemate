"""The story's backbone conversation: the one session its primary turns share."""
from __future__ import annotations

from workhorse.pyflow import Workflow


def story_chain(slug: str) -> str:
    """The chain name a story's primary turns share across lanes."""
    return f"story:{slug}"


def backbone(flow: Workflow) -> str:
    """The chain the story on this flow's `ctx` runs its primary turns on."""
    return story_chain(flow.ctx.story_slug)


__all__ = ["backbone", "story_chain"]
