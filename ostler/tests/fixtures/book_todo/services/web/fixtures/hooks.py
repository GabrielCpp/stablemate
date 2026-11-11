"""What changes around the app, outside its screens: the day, the store behind
it, the network under it."""

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


@dataclass(eq=False)
class Network(Fixture):
    offline: bool

    def __str__(self) -> str:
        return "offline" if self.offline else "online"
