from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from ..commands import Control, Look
from ..events import ParkARun
from ..fixtures import park, rewind, status


class RewindAStoppedRun(Journey):
    """A run stopped at a gate with a stale parameter. The operator reads its checkpoint, moves it back to its start,
    which drops the parameter and frees the gate, and reads the checkpoint again."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            ParkARun(park()),
            Control(status()),
            Control(rewind()),
            Look(),
            Control(status(run="parked")),
            Control(rewind(run="parked")),
        )
