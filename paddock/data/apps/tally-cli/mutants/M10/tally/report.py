"""What the ledger says, in the two shapes something downstream can read."""

import csv

from tally.ledger import COLUMNS, currency_of


def summarize(data: dict) -> dict:
    """Total the ledger, and say per person what they put in."""
    per_person: dict[str, int] = {}
    for entry in data["entries"]:
        per_person[entry["who"]] = per_person.get(entry["who"], 0) + int(entry["amount_cents"])
    return {
        "currency": currency_of(data),
        "entries": len(per_person),
        "total_cents": sum(per_person.values()),
        "per_person": dict(sorted(per_person.items())),
    }


def export_rows(data: dict, path) -> int:
    """Write every entry to `path` as CSV, header first, and say how many rows that was."""
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for entry in data["entries"]:
            writer.writerow([entry[column] for column in COLUMNS])
    return len(data["entries"])
