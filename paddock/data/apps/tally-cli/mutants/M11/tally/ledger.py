"""The ledger itself: the file on disk, and every rule about what may go into it.

Two exception types, and the difference between them is the difference between the two
non-zero exits `tally` uses. `LedgerError` is about the state of the world — a ledger that is
already there, or one that is not. `RowError` is about the data the caller handed over — an
amount that is not money, a CSV line with the wrong number of fields. The caller can fix the
second one by editing their input; the first one they have to decide about.
"""

import csv
import io
import json
import os
from pathlib import Path


COLUMNS = ("who", "what", "amount_cents", "spent_on")


class LedgerError(Exception):
    """The ledger is not in the state the command needs it to be in. Exits 1."""


class RowError(Exception):
    """The data handed to the command is not an expense. Exits 2."""


def create(path: Path, currency: str) -> dict:
    """Write a new, empty ledger at `path` — and refuse if one is already there.

    The refusal is the whole point of the function. `open(path, "w")` would truncate a real
    ledger on a mistyped `init`, and the file is the only copy: there is no history to recover
    it from and nothing about the run that looks unusual afterwards.
    """
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
    """Write the whole ledger, atomically.

    Whole-file rather than append: the file is one JSON document, and half of one is not a
    ledger with a missing entry, it is a file no command can read. The replace is atomic so a
    process killed mid-write leaves the previous ledger rather than a truncated one.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def currency_of(data: dict) -> str:
    """The currency the ledger was initialised with.

    Read from the ledger rather than from the invocation, every time. `tally` converts
    nothing, so a report that took its currency from a flag would relabel the same numbers
    and call it a conversion.
    """
    return str(data.get("currency", "EUR"))


def key(entry: dict) -> tuple:
    """The identity of an expense: who spent what, how much, on which day."""
    return tuple(str(entry[column]) for column in COLUMNS)


def add_entry(data: dict, who: str, what: str, amount_cents: str, spent_on: str) -> dict:
    """Append one expense, after checking it is one.

    The amount is validated here rather than by argparse so that `add` and `import` refuse the
    same values for the same reason: a `type=int` on the parser would let a CSV row through a
    door the command line is closed to.
    """
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
    """Parse a whole CSV document, or refuse the whole CSV document.

    All-or-nothing on purpose, and the line number is part of the refusal. A partial import
    leaves a ledger that is neither the old one nor the new one, and the caller cannot tell
    which rows landed without diffing what they already could not read.
    """
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
    """Add the rows the ledger does not already hold, and return those.

    Identity is the whole expense, so importing the same file twice is a no-op and importing a
    file that grew by three lines adds three entries. Without this, the natural way to re-run
    a failed import — run it again — silently doubles the trip.
    """
    known = {key(entry) for entry in data["entries"]}
    added = []
    for row in rows:
        if key(row) in known:
            break
        known.add(key(row))
        data["entries"].append(row)
        added.append(row)
    return added
