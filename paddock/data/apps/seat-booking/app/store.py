"""The seat ledger: the whole of the app's state, on one JSON file."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

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
    """Read-modify-write over one JSON file."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self) -> dict[str, Any]:
        if not self.path.exists():
            return empty_ledger()
        loaded = json.loads(self.path.read_text(encoding="utf-8"))
        ledger = empty_ledger()
        for seat, record in (loaded.get("seats") or {}).items():
            if seat in ledger["seats"]:
                ledger["seats"][seat] = record
        return ledger

    def write(self, ledger: dict[str, Any]) -> None:
        """Atomically, so a reader never sees half a ledger."""
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
