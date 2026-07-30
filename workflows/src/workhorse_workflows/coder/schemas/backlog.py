"""The backlog as a worklist: what was drawn from it, what it seeded, what it recorded.

Ported from the fix loop's four script nodes — `select-next-fix-item.py`,
`seed-fix-story.py`, `prune-fix-item.py` and `mark-fix-blocked.py`. They are one subject
with `append-backlog-item.py`, which fills the same file under the same `## Filed by coder`
heading with the same bullet grammar; `BacklogDrain` (the filing node's model) is re-exported
here so the whole backlog vocabulary reads from one import, while its definition stays in
`schemas/qa.py` where the filing node's flow put it.

Every field is the two-state case — `yes`/`no` with a blank meaning `no` — so every one of
them is a bool. Nothing in this group is a genuine tri-state.
"""
from __future__ import annotations

from workhorse_workflows.coder.schemas._base import CoderResult
from workhorse_workflows.coder.schemas.qa import BacklogDrain


class FixPick(CoderResult):
    """`select-next-fix-item.py` — the next drainable bullet, or "the pool is dry".

    "Drainable" excludes a bullet already annotated `(blocked …)` by `mark_fix_blocked`: a
    permanently stuck item is skipped on every later draw *without being removed*, so it
    stays visible to a human in `docs/backlog.md` and never spins the loop.

    `reason` is the whole of why the answer is what it is, and it is preserved verbatim from
    the script — it is what a run record shows for a drain that found nothing.
    """

    has_fix: bool = False
    fix_bullet_id: str = ""
    fix_bullet_text: str = ""
    reason: str = ""


class FixStorySeed(CoderResult):
    """`seed-fix-story.py` — the single-AC story a drained bullet became.

    The paths are repo-relative, as the script emitted them; the flow joins them onto the
    docs root itself. `bullet_id` is echoed back so the prune/block step at the end of the
    iteration acts on the id this story was seeded from rather than re-reading the backlog.
    """

    epic: str = ""
    epic_dir: str = ""
    story_slug: str = ""
    story_dir: str = ""
    story_path: str = ""
    bullet_id: str = ""
    reason: str = ""


class FixPruned(CoderResult):
    """`prune-fix-item.py` — the shipped fix's bullet is gone from the backlog."""

    pruned: bool = False
    bullet_id: str = ""
    reason: str = ""


class FixBlocked(CoderResult):
    """`mark-fix-blocked.py` — the stuck fix's bullet is annotated in place, not removed.

    `marked` is true for the already-annotated no-op too: the field answers "is this bullet
    now flagged", not "did this call write a byte", which is what makes a resumed iteration
    idempotent.
    """

    marked: bool = False
    bullet_id: str = ""
    reason: str = ""


__all__ = ["BacklogDrain", "FixBlocked", "FixPick", "FixPruned", "FixStorySeed"]
