"""A run groom froze into an archive: its stored summary sits in History, and its files
either hold the telemetry or are gone."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from ostler.book import Actor, Fixture


@dataclass(eq=False)
class Archived(Fixture):
    gone: bool = False

    def __str__(self) -> str:
        return "an archive whose files are gone" if self.gone else "an archived run"

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[Archived]:
        return (archived(), archived(gone=True))


def archived(**fields: Any) -> Archived:
    return Archived(**fields)
