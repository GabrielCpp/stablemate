"""A desk that hears an event: the handler of a service that takes `ticket.changed` off a queue, with the one internal route
a test places the queue's envelope on, and the surface that performs an arrival by its own means."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, replace
from typing import Any

from ostler.book import Arrange, Done, Event, Field, Object, Str
from ostler.book.cast import SOLE
from ostler.book.delivery import Delivery
from ostler.book.domain import Action, Collection, Create, State, Unique, Update
from ostler.book.http import Id

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


@dataclass
class Ticket:
    id: str
    priority: str
    lapsed: bool = False


class Tickets(State):
    tickets = Collection(Ticket, Unique("id"))

    def rows(self) -> tuple[object, ...]:
        return tuple(t.id for t in self.tickets)


class Changed(Event):
    """A ticket was written."""

    name = "ticket.changed"
    source = "zeta.dynamostream"
    detail = Object(ticket_id=Field(Id(Ticket)), snapshot=Field(Object(priority=Field(Str()))))


class Open(Action[str, Tickets]):
    emits = (Changed,)

    @staticmethod
    def reduce(a: str, s: Tickets, by: Any) -> Create:
        return Create(Tickets.tickets, Ticket(a, "high"))

    @staticmethod
    def announces(event: type[Event], a: str, s: Tickets, by: Any) -> dict[str, Any] | None:
        """The ticket id and the priority it was opened with."""
        return {"ticket_id": a, "snapshot": {"priority": s.tickets[a].priority}}


class OpenQuietly(Open):
    @staticmethod
    def announces(event: type[Event], a: str, s: Tickets, by: Any) -> dict[str, Any] | None:
        return None


class Opens:
    carries = Open
    by = SOLE

    def __init__(self, of: str) -> None:
        self.of = of

    def input(self) -> str:
        return self.of

    def __str__(self) -> str:
        return f"opens {self.of}"


class OpensQuietly(Opens):
    carries = OpenQuietly


class Tap(Delivery):
    """A way of travelling that taps: what the app emits waits here until the run reads it."""

    def __init__(self) -> None:
        self.waiting: list[tuple[str, dict[str, Any]]] = []
        self.opened = 0
        self.closed = 0
        self.reads = 0

    def place(self, event: type[Event], detail: dict[str, Any]) -> None:
        return None

    def open_tap(self) -> None:
        self.opened += 1

    def tapped(self) -> list[tuple[str, dict[str, Any]]]:
        self.reads += 1
        out, self.waiting = self.waiting, []
        return out

    def close_tap(self) -> None:
        self.closed += 1


class Emitter(Quiet):
    """A surface whose app emits `ticket.changed` for a ticket it opens, with a stranger's event beside it. `bug` is
    `silent` for no emission, `wrong` for another priority, `stranger` for an event about another's record alone."""

    name = "emitter"

    def __init__(self, tap: Tap, bug: str | None = None) -> None:
        self.tap = tap
        self.bug = bug
        self.tickets: list[str] = []

    def perform(self, step: Any) -> Done:
        self.tickets.append(step.of)
        if self.bug != "silent":
            self.tap.waiting.append(("ticket.changed", {"ticket_id": "S-" + step.of, "snapshot": {"priority": "low"}}))
        if self.bug not in ("silent", "stranger"):
            self.tap.waiting.append(("ticket.changed", {"ticket_id": step.of, "snapshot": {"priority": "low" if self.bug == "wrong" else "high"}}))
        return Done()

    def rows(self) -> tuple[object, ...]:
        return tuple(self.tickets)


class Breached(Event):
    """A ticket's due time went by."""

    name = "ticket.breached"
    source = "zeta.scan"
    detail = Object(ticket_id=Field(Id(Ticket)))


class Write(Action[str, Tickets]):
    @staticmethod
    def reduce(a: str, s: Tickets, by: Any) -> Create:
        return Create(Tickets.tickets, Ticket(a, "high"))


class Lapse(Action[str, Tickets]):
    @staticmethod
    def reduce(a: str, s: Tickets, by: Any) -> Update:
        return Update(Tickets.tickets, a, replace(s.tickets[a], lapsed=True))


class Breach(Action[str, Tickets]):
    """The scan finds a ticket past its due time."""

    clock = "the ticket's due time goes by"
    emits = (Breached,)

    @staticmethod
    def announces(event: type[Event], a: str, s: Tickets, by: Any) -> dict[str, Any] | None:
        return {"ticket_id": a}


class Writes(Arrange[str]):
    does = "A ticket is written."
    carries = Write


class Lapses(Arrange[str]):
    does = "A ticket is written past its due time."
    carries = Lapse


class Breaches(Arrange[str]):
    does = "The clock takes a ticket past its due time."
    carries = Breach


class ScanTap(Tap):
    """A tap whose read waits a moment for the scan to publish, as a read of a queue does."""

    def __init__(self) -> None:
        super().__init__()
        self.lock = threading.Condition()

    def publish(self, event: tuple[str, dict[str, Any]]) -> None:
        with self.lock:
            self.waiting.append(event)
            self.lock.notify_all()

    def tapped(self) -> list[tuple[str, dict[str, Any]]]:
        with self.lock:
            if not self.waiting:
                self.lock.wait(0.002)
            self.reads += 1
            out, self.waiting = self.waiting, []
            return out


class Scanner(Quiet):
    """A surface whose app scans its store on its own loop in its own thread and publishes `ticket.breached` once for every
    ticket written past its due time. `scanning` is False for an app whose scan never runs."""

    name = "scanner"

    def __init__(self, tap: ScanTap, scanning: bool = True) -> None:
        self.tap = tap
        self.scanning = scanning
        self.store: dict[str, bool] = {}
        self.performed: list[object] = []
        self.told: set[str] = set()
        self.stopped = threading.Event()
        self.guard = threading.Lock()
        self.loop = threading.Thread(target=self.scan, daemon=True)

    def start(self) -> None:
        if self.scanning:
            self.loop.start()

    def stop(self) -> None:
        self.stopped.set()
        if self.loop.is_alive():
            self.loop.join()

    def scan(self) -> None:
        while not self.stopped.wait(0.001):
            with self.guard:
                due = [t for t, lapsed in self.store.items() if lapsed and t not in self.told]
                self.told.update(due)
            for ticket in due:
                self.tap.publish(("ticket.breached", {"ticket_id": ticket}))

    def perform(self, step: Any) -> Done:
        self.performed.append(step)
        ticket = str(step.of)
        with self.guard:
            self.store[ticket] = isinstance(step, Lapses) or self.store.get(ticket, False)
        return Done()

    def rows(self) -> tuple[object, ...]:
        return tuple(self.store)
