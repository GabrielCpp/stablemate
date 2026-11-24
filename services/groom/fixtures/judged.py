"""A workflow's ended runs as groom's History holds them: the runs of one workflow that
ended before, and the one run an operator judges against their median."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from ostler.book import Actor, Fixture

from .push import _next_name

PEERS = (1.0, 2.0, 3.0, 4.0, 5.0)


@dataclass(eq=False)
class Judged(Fixture):
    workflow: str = ""
    peers: tuple[float, ...] = PEERS
    each: float = 12.0
    ending: str = "success"
    items: int = 2
    estimate: bool = False

    def __str__(self) -> str:
        return f"{self.workflow}: ${self.each} per item against {len(self.peers)} runs"

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[Judged]:
        return (judging(),)


def judging(**fields: Any) -> Judged:
    return Judged(workflow=_next_name(), **fields)
