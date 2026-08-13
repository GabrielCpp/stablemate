"""The seat ledger: the whole of the app's state, on one JSON file.

A file rather than a process dictionary, and re-read on every request rather than cached,
because one of the observations the book declares is `persists` — a booking has to survive
a restart, and a store that only ever answers out of the memory of the process that wrote
it cannot tell a commit from a cache. Keeping the read on the request path makes the
guarantee cheap to state and impossible to fake.

Concurrency is a compare-and-swap on a per-seat integer `version`, bumped by every
transition. Confirming a hold quotes the version it saw; a request quoting an older one is
refused. That is what makes `conflict_on_stale` observable at all: a plain write-then-read
cannot distinguish an unconditional overwrite from a real CAS, and only a stale write that
comes back 409 can.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

#: Three rows of four. Small enough that a QA scenario can assert the whole map by count,
#: large enough that "released seat A, perturbed seat B" is a distinguishable defect.
ROWS = ("A", "B", "C")
NUMBERS = (1, 2, 3, 4)

FREE = "free"
HELD = "held"
BOOKED = "booked"


def seat_ids() -> list[str]:
    return [f"{row}{number}" for row in ROWS for number in NUMBERS]


def empty_ledger() -> dict[str, Any]:
    return {
        "seats": {
            seat: {"state": FREE, "version": 0, "hold": None, "booking": None}
            for seat in seat_ids()
        }
    }


class Store:
    """Read-modify-write over one JSON file. Every mutation lands or none of it does."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self) -> dict[str, Any]:
        if not self.path.exists():
            return empty_ledger()
        loaded = json.loads(self.path.read_text(encoding="utf-8"))
        # A ledger written by an older seat map is completed rather than rejected: a seat
        # the file does not mention is free, which is exactly what an absent row means.
        ledger = empty_ledger()
        for seat, record in (loaded.get("seats") or {}).items():
            if seat in ledger["seats"]:
                ledger["seats"][seat] = record
        return ledger

    def write(self, ledger: dict[str, Any]) -> None:
        """Atomically, so a reader never sees half a ledger.

        `os.replace` onto the same filesystem is the whole mechanism — a torn write here
        would show up as a `persists` failure attributed to the wrong behaviour.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(ledger, handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
