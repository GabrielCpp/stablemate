from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from ..commands import Look, SeedAdd, SeedRemove
from ..fixtures import seed_add, seed_remove


class WriteSeeds(Journey):
    """A planner lists two seeds under the second epic, rewrites the first with a status and a layer, and takes both
    out again. The watch reads the epic's page after each step."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            SeedAdd(seed_add("0002-second", "SD-3")),
            Look(),
            SeedAdd(seed_add("0002-second", "SD-4", status="researched", layer="frontend")),
            Look(),
            SeedAdd(seed_add("0002-second", "SD-3", status="researched", layer="frontend")),
            Look(),
            SeedRemove(seed_remove("0002-second", "SD-3")),
            SeedRemove(seed_remove("0002-second", "SD-4")),
            Look(),
        )
