"""The story's backbone conversation, and the one rule that bounds it.

A story is implemented, repaired and review-applied by the same agent in the same
conversation: the fixer that already read the code it is fixing does not spend its first
minutes re-reading it, and the applier that wrote the line a reviewer objects to knows why
it is there. That is what `session_id` threads between lanes.

The cost of that is context length, and a long context is where a cheap turn stops being a
cheap turn. So the conversation is recycled on a turn count rather than allowed to grow: past
the cap, the next turn opens a fresh chain, seeded by the payload its caller renders — the
failure report, the changed files, the review findings — instead of by the history.

Plain functions, not nodes: they decide nothing that belongs in a checkpoint of their own,
and the count they operate on is a state parameter of the flow that holds it.
"""
from __future__ import annotations

from workhorse.pyflow import Workflow


def story_chain(slug: str) -> str:
    """The chain name a story's primary turns share across lanes.

    Every lane naming the same story lands in the same conversation. The literal lives
    here because four lanes have to agree on it — a lane that spells it its own way is a
    lane that quietly reviews its own diff in a fresh context.

    A lane entered with a `session_id` from an earlier lane seeds *this* key with it
    (`flow.seed_session(story_chain(slug), session_id)`, once, in `setup`) rather than
    using the id as a key of its own: an id is an opaque string, and a chain named after
    one is a chain nobody else can name.
    """
    return f"story:{slug}"


def spend_turn(flow: Workflow, chain: str, turns: int, cap: int) -> int:
    """Count one turn onto `chain`, recycling it when it is full.

    Called immediately *before* the turn it counts, so the recycling lands on the turn that
    would otherwise have opened the over-long context. The count restarts at one rather than
    zero because the turn about to run is the first of the new conversation. A cap of 0 never
    recycles.
    """
    if cap and turns >= cap:
        flow.logger.info(
            "the story conversation reached %d turns — starting a fresh one", cap
        )
        flow.reset_session(chain)
        return 1
    return turns + 1


__all__ = ["spend_turn", "story_chain"]
