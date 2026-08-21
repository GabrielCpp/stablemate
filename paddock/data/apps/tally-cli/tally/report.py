"""What the ledger says, in the two shapes something downstream can read.

Neither function prints. `summarize` hands back a dict and `export_rows` writes a named file,
so the decision about which stream a byte goes to is made in exactly one place — `tally.cli` —
and a report that has to survive a pipe cannot be corrupted by a progress line added here.
"""

import csv

from tally.ledger import COLUMNS, currency_of


def summarize(data: dict) -> dict:
    """Total the ledger, and say per person what they put in.

    `total_cents` is the sum of `per_person`, always: the two are computed from one pass so a
    reader can check the report against itself without re-reading the ledger.
    """
    per_person: dict[str, int] = {}
    for entry in data["entries"]:
        per_person[entry["who"]] = per_person.get(entry["who"], 0) + int(entry["amount_cents"])
    return {
        "currency": currency_of(data),
        "entries": len(data["entries"]),
        "total_cents": sum(per_person.values()),
        "per_person": dict(sorted(per_person.items())),
    }


def export_rows(data: dict, path) -> int:
    """Write every entry to `path` as CSV, header first, and say how many rows that was.

    The header is written unconditionally, including for an empty ledger. An export whose
    header appears only when there is data is an export whose shape depends on its content,
    and the first thing every reader of a CSV does is skip line one.
    """
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for entry in data["entries"]:
            writer.writerow([entry[column] for column in COLUMNS])
    return len(data["entries"])
