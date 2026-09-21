"""The ledger itself: the file on disk, and every rule about what may go into it."""

import csv
import io
import json
import os
from pathlib import Path


COLUMNS = ("who", "what", "amount_cents", "spent_on")


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


def key(entry: dict) -> tuple:
    """The identity of an expense: who spent what, how much, on which day."""
    return tuple(str(entry[column]) for column in COLUMNS)


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
    if cents <= 0:
        raise RowError(f"amount {cents} is not positive")
    return cents


def parse_rows(text: str) -> list[dict]:
    """Parse a whole CSV document, or refuse the whole CSV document."""
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise RowError("line 1: the file is empty")
    if tuple(field.strip() for field in rows[0]) != COLUMNS:
        raise RowError(f"line 1: header must be {','.join(COLUMNS)}")

    parsed = []
    for number, row in enumerate(rows[1:], start=2):
        if not row:
            continue
        if len(row) != len(COLUMNS):
            raise RowError(f"line {number}: expected {len(COLUMNS)} fields, found {len(row)}")
        entry: dict = dict(zip(COLUMNS, (field.strip() for field in row)))
        try:
            entry["amount_cents"] = _cents(entry["amount_cents"])
        except RowError as bad:
            raise RowError(f"line {number}: {bad}") from None
        parsed.append(entry)
    return parsed


def merge(data: dict, rows: list[dict]) -> list[dict]:
    """Add the rows the ledger does not already hold, and return those."""
    known = {key(entry) for entry in data["entries"]}
    added = []
    for row in rows:
        if key(row) in known:
            continue
        data["entries"].append(row)
        added.append(row)
    return added
