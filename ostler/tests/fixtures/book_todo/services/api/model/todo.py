"""What the service keeps for one todo, and what a reader sees listed. Status is
never stored: it is read off the due date against the service's today."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

USERS = ("ana", "bo")
STATUSES = ("unscheduled", "scheduled", "overdue")


@dataclass(frozen=True)
class TodoRecord:
    id: str
    title: str
    description: str | None
    due_on: date | None
    assignee: str | None

    def status(self, today: date) -> str:
        if self.due_on is None:
            return "unscheduled"
        return "scheduled" if self.due_on >= today else "overdue"

    def __str__(self) -> str:
        bits = [f"{self.title} [{self.id[:8]}]"]
        if self.due_on:
            bits.append(f"due {self.due_on.isoformat()}")
        if self.assignee:
            bits.append(f"for {self.assignee}")
        if self.description:
            bits.append(repr(self.description))
        return " · ".join(bits)


@dataclass(frozen=True)
class Day:
    today: date


@dataclass(frozen=True)
class Row:
    id: str
    title: str
    description: str | None
    due_on: str | None
    assignee: str | None
    status: str

    def __str__(self) -> str:
        bits = [self.title, self.status]
        if self.due_on:
            bits.append(f"due {self.due_on}")
        if self.assignee:
            bits.append(f"for {self.assignee}")
        if self.description:
            bits.append(repr(self.description))
        return " · ".join(bits)
