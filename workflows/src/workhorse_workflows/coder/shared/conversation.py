"""The story's backbone conversation, and the one rule that bounds it."""
from __future__ import annotations

from workhorse.pyflow import Workflow


def story_chain(slug: str) -> str:
    """The chain name a story's primary turns share across lanes."""
    return f"story:{slug}"


def backbone(flow: Workflow) -> str:
    """The chain the story on this flow's `ctx` runs its primary turns on."""
    return story_chain(flow.ctx.story_slug)


def spend_turn(flow: Workflow, chain: str, turns: int, cap: int) -> int:
    """Count one turn onto `chain`, recycling it when it is full."""
    if cap and turns >= cap:
        flow.logger.info(
            "the story conversation reached %d turns — starting a fresh one", cap
        )
        flow.reset_session(chain)
        return 1
    return turns + 1


__all__ = ["backbone", "spend_turn", "story_chain"]
