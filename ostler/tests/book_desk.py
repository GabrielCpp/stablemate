"""A desk that hears an event: the handler of a service that takes `ticket.changed` off a queue, with the one internal route
a test places the queue's envelope on, and the surface that performs an arrival by its own means."""

from __future__ import annotations

import json
from typing import Any

from ostler.book import Done, Event, Field, Object, Str
from ostler.book.delivery import Delivery

from book_fakes import Quiet


class TicketChanged(Event):
    """The stored record of a ticket was written."""

    name = "ticket.changed"
    source = "zeta.dynamostream"
    detail = Object(snapshot=Field(Object(team=Field(Str()), priority=Field(Str()))), ticket_id=Field(Str()), by=Field(Str()))


class Desk:
    """`bug` names what the handler gets wrong: `applies-again` applies a ticket it already heard a second time."""

    def __init__(self, bug: str | None = None) -> None:
        self.bug = bug
        self.heard: set[str] = set()
        self.priorities: dict[str, str] = {}
        self.count = 0

    def hear(self, detail: dict[str, Any]) -> None:
        ticket = detail["ticket_id"]
        if ticket in self.heard and self.bug != "applies-again":
            return
        self.heard.add(ticket)
        self.priorities[ticket] = detail["snapshot"]["priority"]
        self.count += 1

    def queue(self, envelope: dict[str, Any]) -> None:
        """The internal route: the envelope a queue would hold, taken to the handler."""
        assert envelope["detail-type"] == TicketChanged.name
        self.hear(json.loads(envelope["detail"]))


class ToQueue(Delivery):
    def __init__(self, desk: Desk) -> None:
        self.desk = desk
        self.placed: list[dict[str, Any]] = []

    def place(self, event: type[Event], detail: dict[str, Any]) -> None:
        self.placed.append(detail)
        self.desk.queue({"detail-type": event.name, "source": event.source, "detail": json.dumps(detail)})


class DeskSurface(Quiet):
    name = "desk"

    def __init__(self, desk: Desk) -> None:
        self.desk = desk
        self.performed: list[object] = []

    def perform(self, step: Any) -> Done:
        self.performed.append(step)
        self.desk.hear({"ticket_id": str(step.of), "by": "surface", "snapshot": {"priority": "high", "team": "a"}})
        return Done()

    def rows(self) -> tuple[object, ...]:
        return (self.desk.count,)
