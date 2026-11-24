"""The Activity tab of a run that reported no telemetry."""

from __future__ import annotations

from dataclasses import dataclass

from ostler.book import Action, Actor, Transaction

from ..fixtures import Push
from ..model.state import Dashboard


@dataclass(frozen=True)
class Note:
    """What the Activity tab of a run says in place of a timeline."""

    text: str

    def __str__(self) -> str:
        return self.text


NO_TELEMETRY = "No telemetry for this run. It was recorded before telemetry, or it exports to another collector."


class ReadActivityTab(Action[Push, Dashboard]):
    accept = Push

    @staticmethod
    def reduce(a: Push, s: Dashboard, by: Actor | None) -> Transaction:
        return Transaction(says=(Note(NO_TELEMETRY),))


