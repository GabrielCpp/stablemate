"""The ledger itself: the file on disk, and every rule about what may go into it.

Two exception types, and the difference between them is the difference between the two
non-zero exits `tally` uses. `LedgerError` is about the state of the world — a ledger that is
already there, or one that is not. `RowError` is about the data the caller handed over — an
amount that is not money, a CSV line with the wrong number of fields. The caller can fix the
second one by editing their input; the first one they have to decide about.
"""

import json
import os
from pathlib import Path


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
