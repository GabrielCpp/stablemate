"""Taking a seat off the market, and giving it back.

One module for the pair because the book cites a transition by symbol and grounds the
obligation there. `hold` and `release` are the two that only ever move a seat between
`free` and `held`; the booking a hold leads to is `confirm.py`'s.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.booking import SEAT_NOT_HELD, Conflict, Refused, seat_record
from app.store import BOOKED, FREE, HELD, Store

SEAT_UNAVAILABLE = Refused(409, "Seat Unavailable")


def hold(store: Store, seat: str) -> dict[str, Any]:
    """Put a free seat on hold, and return the hold plus the version to confirm against."""
    ledger = store.read()
    record = seat_record(ledger, seat)
    if record["state"] == BOOKED:
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
    record = seat_record(ledger, seat)
    if record["state"] != HELD:
        raise Conflict(SEAT_NOT_HELD)
    record["state"] = FREE
    record["version"] += 1
    record["hold"] = None
    store.write(ledger)
