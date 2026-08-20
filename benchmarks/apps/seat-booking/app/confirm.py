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

    `version` is the compare-and-swap token. Anyone who held the seat, lost it, and comes
    back with the number they were given is refused — which is the one observation that
    separates this from an unconditional write.

    The version is compared *before* the state, and the order is load-bearing rather than
    incidental: the double-spend this exists to refuse is a caller whose hold has already
    been taken and re-booked by someone else, so the seat is no longer `held` and a
    state-first check would answer `Seat Not Held` for what is precisely a stale hold. A
    caller quoting the seat's current version still falls through to the state check, so
    the never-held case keeps its own refusal.
    """
    ledger = store.read()
    record = seat_record(ledger, seat)
    if record["version"] != version:
        raise Conflict(STALE_HOLD)
    if record["state"] != HELD:
        raise Conflict(SEAT_NOT_HELD)
    booking_id = uuid.uuid4().hex
    record["state"] = BOOKED
    record["version"] += 1
    record["hold"] = None
    record["booking"] = {"id": booking_id, "name": name}
    store.write(ledger)
    return {"id": booking_id, "seat": seat, "name": name}
