from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from ..commands import Conflict, SeedAdd, SeedRemove, SetStatus
from ..fixtures import ALPHA, conflict, seed_add, seed_remove, set_status


class WrongTurns(Journey):
    """A planner slips. They list a seed under an epic that does not exist, list a seed with a status and a layer
    the registry lacks, remove a seed that is not there, give a story an empty status
    or one made of spaces and tabs and then `In progress`, and name a story that does not exist or give a conflict
    no text."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            SeedAdd(seed_add("0009", "SD-3")),
            SeedAdd(seed_add("0002-second", "SD-3", status="weird")),
            SeedAdd(seed_add("0002-second", "SD-3", layer="cloud")),
            SeedRemove(seed_remove("0002-second", "SD-3")),
            SetStatus(set_status(ALPHA, "")),
            SetStatus(set_status(ALPHA, "  \t ")),
            SetStatus(set_status("TST-NOPE", "")),
            SetStatus(set_status(ALPHA, "In progress")),
            SetStatus(set_status("TST-NOPE", "in-progress")),
            Conflict(conflict(ALPHA, None)),
            Conflict(conflict(ALPHA, "criteria disagree", clear=True)),
            Conflict(conflict("TST-NOPE", "criteria disagree")),
        )
