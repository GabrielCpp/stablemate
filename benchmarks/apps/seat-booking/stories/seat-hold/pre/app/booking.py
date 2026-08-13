"""What the seat map is read through.

Kept apart from the HTTP layer on purpose: every rule the book states as a `does:` is a function
here, so a scenario that fails names the projection rather than the route. `service.py` serialises
and does no deciding of its own.
"""

from __future__ import annotations

from typing import Any

from app.store import Store


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
