from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from ..commands import Conflict, Look, SetStatus
from ..fixtures import ALPHA, BRAVO, conflict, set_status


class TrackAStory(Journey):
    """A planner moves the story alpha through its statuses, records a conflict in its criteria, replaces the conflict
    with another, and clears it. A second story keeps its own status throughout."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            SetStatus(set_status(ALPHA, "in-progress")),
            Look(),
            Conflict(conflict(ALPHA, "criteria disagree")),
            Look(),
            Conflict(conflict(ALPHA, "specs contradict")),
            SetStatus(set_status(BRAVO, "Blocked: waiting")),
            Look(),
            Conflict(conflict(ALPHA, None, clear=True)),
            SetStatus(set_status(ALPHA, "Not started")),
            Look(),
        )
