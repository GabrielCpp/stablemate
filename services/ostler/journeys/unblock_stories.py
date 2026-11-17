from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from ..commands import Look, SetStatus, Unblock
from ..fixtures import ALPHA, BRAVO, SX, set_status, unblock


class UnblockStories(Journey):
    """A planner finds stories a run gave up on and sets them going again. They unblock one story and then an epic's,
    unblock a story that is not blocked, set two stories aside again and unblock every story to a status of their own
    choosing, and find unblock refusing a call that names nothing, two scopes or something that is not there."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            SetStatus(set_status(ALPHA, "Blocked: waiting")),
            SetStatus(set_status(SX, "Blocked: waiting")),
            Look(),
            Unblock(unblock(ALPHA)),
            Unblock(unblock(ALPHA)),
            Look(),
            SetStatus(set_status(ALPHA, "Blocked: waiting")),
            SetStatus(set_status(BRAVO, "Blocked: waiting")),
            Unblock(unblock(None, "first")),
            Look(),
            Unblock(unblock(None, "second", status="in-progress")),
            Look(),
            SetStatus(set_status(BRAVO, "Blocked: waiting")),
            Unblock(unblock(None, None, all=True, status="in-progress")),
            Unblock(unblock(None, None, all=True)),
            Look(),
            Unblock(unblock()),
            Unblock(unblock(ALPHA, "first")),
            Unblock(unblock(ALPHA, all=True)),
            Unblock(unblock("TST-NOPE")),
            Unblock(unblock(None, "nope")),
        )
