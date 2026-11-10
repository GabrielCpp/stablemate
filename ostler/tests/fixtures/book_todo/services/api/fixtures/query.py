"""The filters a client sends to list todos."""

from __future__ import annotations

from dataclasses import dataclass

from ostler.book import Fixture


@dataclass(eq=False)
class Query(Fixture):
    text: str | None = None
    assignee: str | None = None
    status: str | None = None

    def __str__(self) -> str:
        return " ".join(f"{k}={v}" for k, v in vars(self).items() if v is not None) or "everything"
