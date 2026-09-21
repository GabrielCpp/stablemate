"""The ledger itself: the file on disk, and every rule about what may go into it."""

import json
import os
from pathlib import Path


class LedgerError(Exception):
    """The ledger is not in the state the command needs it to be in."""


class RowError(Exception):
    """The data handed to the command is not an expense."""


def create(path: Path, currency: str) -> dict:
    """Write a new, empty ledger at `path` — and refuse if one is already there."""
    if path.exists():
        raise LedgerError(f"{path} already exists; refusing to overwrite it")
    data = {"currency": currency, "entries": []}
    save(path, data)
    return data


def load(path: Path) -> dict:
    """Read the ledger back, or say plainly that there is not one."""
    if not path.exists():
        raise LedgerError(f"{path} does not exist; run `tally init` first")
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, data: dict) -> None:
    """Write the whole ledger, atomically."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def currency_of(data: dict) -> str:
    """The currency the ledger was initialised with."""
    return str(data.get("currency", "EUR"))


def add_entry(data: dict, who: str, what: str, amount_cents: str, spent_on: str) -> dict:
    """Append one expense, after checking it is one."""
    entry = {
        "who": who,
        "what": what,
        "amount_cents": _cents(amount_cents),
        "spent_on": spent_on,
    }
    data["entries"].append(entry)
    return entry


def _cents(amount: object) -> int:
    """An amount is a positive whole number of cents, or it is not an amount."""
    try:
        cents = int(str(amount))
    except (TypeError, ValueError):
        raise RowError(f"amount {amount!r} is not a whole number of cents") from None
    return cents
