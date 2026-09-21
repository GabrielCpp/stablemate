"""Taking a seat off the market, and giving it back."""

from __future__ import annotations

import uuid
from typing import Any

from app.booking import SEAT_NOT_HELD, Conflict, Refused, seat_record
from app.store import FREE, HELD, Store

SEAT_UNAVAILABLE = Refused(409, "Seat Unavailable")


def hold(store: Store, seat: str) -> dict[str, Any]:
    """Put a free seat on hold, and return the hold plus the version to confirm against."""
    ledger = store.read()
    record = seat_record(ledger, seat)
    if record["state"] != FREE:
        raise Conflict(SEAT_UNAVAILABLE)
    hold_id = uuid.uuid4().hex
    record["state"] = HELD
    record["version"] += 1
    record["hold"] = {"id": hold_id}
    store.write(ledger)
    return {"id": hold_id, "seat": seat, "version": record["version"]}


def release(store: Store, seat: str) -> None:
    """Return a held seat to free, touching that seat and no other."""
    ledger = store.read()
    record = seat_record(ledger, seat)
    if record["state"] != HELD:
        raise Conflict(SEAT_NOT_HELD)
    record["state"] = FREE
    record["version"] += 1
    record["hold"] = None
    store.write(ledger)
