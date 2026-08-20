"""Spending a hold on a booking, once.

Its own module for the same reason `hold.py` is one: the compare-and-swap rule the book
states on `confirm` is grounded at this symbol, so a defect seeded in it localizes here and
nowhere else.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.booking import SEAT_NOT_HELD, Conflict, Refused, seat_record
from app.store import BOOKED, HELD, Store

STALE_HOLD = Refused(409, "Stale Hold")


def confirm(store: Store, seat: str, *, version: int, name: str) -> dict[str, Any]:
    """Turn a hold into a booking, but only for a caller quoting the version it saw.

    The caller sends the version it saw, which the book says is compared against the
    seat's current one. It is read off the request and not used.
    """
    ledger = store.read()
    record = seat_record(ledger, seat)
    if record["state"] != HELD:
        raise Conflict(SEAT_NOT_HELD)
    booking_id = uuid.uuid4().hex
    record["state"] = BOOKED
    record["version"] += 1
    record["hold"] = None
    record["booking"] = {"id": booking_id, "name": name}
    store.write(ledger)
    return {"id": booking_id, "seat": seat, "name": name}
