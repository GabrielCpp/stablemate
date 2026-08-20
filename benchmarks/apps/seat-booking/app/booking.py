"""What a seat is: the projection every surface reads, and the refusals it can raise.

Kept apart from the HTTP layer on purpose: every rule the book states as a `does:` or a
`raises:` is a function in this package, so a scenario that fails names the transition
rather than the route. `service.py` translates the `Refused` exceptions below into status
codes and does no deciding of its own.

The transitions themselves live one to a module — `hold.py`, `confirm.py` — because the
book grounds an obligation at the symbol it cites, and two transitions sharing a file would
share that file's grounding: a defect seeded in either would localize to neither. What
stays here is what more than one of them needs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.store import Store


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
SEAT_NOT_HELD = Refused(409, "Seat Not Held")


def seat_record(ledger: dict[str, Any], seat: str) -> dict[str, Any]:
    """The seat's row in the ledger, or the refusal for an id the showing does not have."""
    record = ledger["seats"].get(seat)
    if record is None:
        raise Conflict(NO_SUCH_SEAT)
    return record


def seat_map(store: Store) -> list[dict[str, Any]]:
    """Every seat, in row-then-number order, whatever state it is in.

    The whole map rather than the free ones: a client that only ever hears about free seats
    cannot render a seat map, and a scenario counting rows could not tell an empty theatre
    from a sold-out one.

    A booked seat carries the booking it is holding. Without it the map publishes no field
    that distinguishes one booking from another, and the durability criterion the booking
    story is judged on — still booked, *under the same name*, after a restart — would be
    asking QA to prove a claim through a field the API never exposes.
    """
    ledger = store.read()
    return [
        {
            "id": seat,
            "row": seat[0],
            "number": int(seat[1:]),
            "state": record["state"],
            "version": record["version"],
            **({"booking": record["booking"]} if record["booking"] else {}),
        }
        for seat, record in sorted(ledger["seats"].items())
    ]
