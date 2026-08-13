"""The transitions a seat can make, and the errors each refuses with.

Kept apart from the HTTP layer on purpose: every rule the book states as a `does:` or a
`raises:` is a function here, so a scenario that fails names the transition rather than the
route. `service.py` translates the `Refused` exceptions below into status codes and does no
deciding of its own.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from app.store import FREE, HELD, Store


@dataclass(frozen=True)
class Refused:
    """A transition the ledger would not make, and the title the response carries."""

    status: int
    title: str


class Conflict(Exception):
    def __init__(self, refusal: Refused) -> None:
        super().__init__(refusal.title)
        self.refusal = refusal


NO_SUCH_SEAT = Refused(404, "No Such Seat")
SEAT_UNAVAILABLE = Refused(409, "Seat Unavailable")
SEAT_NOT_HELD = Refused(409, "Seat Not Held")


def _seat(ledger: dict[str, Any], seat: str) -> dict[str, Any]:
    record = ledger["seats"].get(seat)
    if record is None:
        raise Conflict(NO_SUCH_SEAT)
    return record


def seat_map(store: Store) -> list[dict[str, Any]]:
    """Every seat, in row-then-number order, whatever state it is in.

    The whole map rather than the free ones: a client that only ever hears about free seats
    cannot render a seat map, and a scenario counting rows could not tell an empty theatre
    from a sold-out one.
    """
    ledger = store.read()
    return [
        {
            "id": seat,
            "row": seat[0],
            "number": int(seat[1:]),
            "state": record["state"],
            "version": record["version"],
        }
        for seat, record in sorted(ledger["seats"].items())
    ]


def hold(store: Store, seat: str) -> dict[str, Any]:
    """Put a free seat on hold, and return the hold plus the version to confirm against."""
    ledger = store.read()
    record = _seat(ledger, seat)
    if record["state"] != FREE:
        raise Conflict(SEAT_UNAVAILABLE)
    hold_id = uuid.uuid4().hex
    record["state"] = HELD
    record["version"] += 1
    record["hold"] = {"id": hold_id}
    store.write(ledger)
    return {"id": hold_id, "seat": seat, "version": record["version"]}


def release(store: Store, seat: str) -> None:
    """Return a held seat to free, touching that seat and no other.

    The narrowness is the point rather than an optimisation: releasing one seat by
    rewriting the whole map from a rebuilt default is a defect nothing but a key-inventory
    comparison of the neighbours would catch.
    """
    ledger = store.read()
    record = _seat(ledger, seat)
    if record["state"] != HELD:
        raise Conflict(SEAT_NOT_HELD)
    record["state"] = FREE
    record["version"] += 1
    record["hold"] = None
    store.write(ledger)
