"""`fix` — drain the coder's own backlog, one filed item at a time.

Nothing hands off to this flow: the main graph carries its **own** copy of the drain,
riding inside an epic's story chain and committing nothing of its own. This package is the
copy you enter directly (`workhorse run coder fix`), with no epic and no story selected.

Because the two copies run the same nodes, none of them is here: the picking, pruning and
blocking are in `shared/backlog.py`, the story spine in `shared/story.py`, and the
implementation loop in `shared/dev.py`. `flow.py` is the machine, and `BLOCKED_NOTE` — the
marker the main graph also writes — is the one name it exports upward.
"""
from __future__ import annotations

from workhorse_workflows.coder.fix.flow import BLOCKED_NOTE, Fix

__all__ = ["BLOCKED_NOTE", "Fix"]
