"""What the app lists for one todo, and what a reader sees in a row. Status is
never stored: it is read off the due date against today. A row never shows the
description."""

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
        return " · ".join(bits)


@dataclass(frozen=True)
class Row:
    title: str
    due_on: str | None
    assignee: str | None
    status: str

    def __str__(self) -> str:
        bits = [self.title, self.status]
        if self.due_on:
            bits.append(f"due {self.due_on}")
        if self.assignee:
            bits.append(f"for {self.assignee}")
        return " · ".join(bits)
