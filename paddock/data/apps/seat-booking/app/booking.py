"""What a seat is: the projection every surface reads, and the refusals it can raise."""

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
    """Every seat, in row-then-number order, whatever state it is in."""
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
