"""What an operator types into a run's answer box: the answer, and the run it is for."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from ostler.book import Actor, Fixture


@dataclass(eq=False)
class Reply(Fixture):
    container_id: str | None = None
    answer: str | None = None

    def __str__(self) -> str:
        return f"answer {self.answer} to {self.container_id}"

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[Reply]:
        return tuple(cls(container_id=run.container_id, answer="yes") for run in state.runs if run.gates)


def replying(container_id: str | None, answer: str = "yes") -> Reply:
    return Reply(container_id=container_id, answer=answer)
