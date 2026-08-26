"""The story's backbone conversation, and the one rule that bounds it.

A story is implemented, repaired and review-applied by the same agent in the same
conversation: the fixer that already read the code it is fixing does not spend its first
minutes re-reading it, and the applier that wrote the line a reviewer objects to knows why
it is there. That is what the story's chain key buys, and why every lane derives the same
one from the story slug instead of being handed a session id: the chain file lives in the
run directory, so a lane that names the key finds the conversation the lane before it left,
and a lane run on its own — a replay, a standalone PR review — finds nothing and starts
cold, which is the honest answer rather than a missing parameter.

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

    Derived from the slug and nothing else, so no lane has to be *told* which conversation
    it is joining. Handed-off sub-flows share their parent's run directory, and the chain
    file lives there, so `dev` opening the conversation is all it takes for `review`,
    `docs` and `qa` to find it — and nothing outside the run can point a lane at a
    conversation, which a settable session id would have allowed.
    """
    return f"story:{slug}"


def backbone(flow: Workflow) -> str:
    """The chain the story on this flow's `ctx` runs its primary turns on.

    The one-liner every lane held its own copy of. Derived from the slug on `ctx`, so a
    lane names the conversation an earlier lane left without being handed anything, and
    stays distinct from the narrower repair chains each lane keys for itself.
    """
    return story_chain(flow.ctx.story_slug)


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


__all__ = ["backbone", "spend_turn", "story_chain"]
