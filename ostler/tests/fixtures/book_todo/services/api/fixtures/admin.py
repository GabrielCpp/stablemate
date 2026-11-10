"""What the test build's admin endpoints take."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ostler.book import Fixture


@dataclass(eq=False)
class Clock(Fixture):
    today: date | str

    def __str__(self) -> str:
        return str(self.today)


@dataclass(eq=False)
class Switch(Fixture):
    down: bool

    def __str__(self) -> str:
        return "down" if self.down else "up"
