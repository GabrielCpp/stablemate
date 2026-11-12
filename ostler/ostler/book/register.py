"""The register of underspecified fields a book keeps for its product owner: a markdown file beside the
service that a run reads, and writes when asked. An entry stands until the owner answers; the answer
removes it and becomes a change of the model, an `ignores=` with the owner's reason, or a defect."""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass, field
from datetime import date

from ostler.book.inputs import Tried, Twinned

FILE = "UNDERSPECIFIED.md"
TITLE = "# Underspecified"
INTRO = ("Fields the model reads one way along a dimension and the app answers apart, waiting for the "
         "product owner. A run reports each as known. The owner's answer removes the entry.")
LABELS = ("dimension", "values", "first answer", "second answer", "first seen")
LIMIT = 300


@dataclass(frozen=True)
class Entry:
    key: str
    dimension: str
    values: str
    first: str
    second: str
    seen: str


@dataclass
class Settled:
    """What a run made of its findings against the register: the findings the register holds, the entries
    this run adds, and the entries whose pair no longer splits."""

    known: list[Twinned] = field(default_factory=list)
    fresh: list[Entry] = field(default_factory=list)
    stale: list[Entry] = field(default_factory=list)


def path(module: str) -> str:
    return os.path.join(os.path.dirname(importlib.import_module(f"{module}.service").__file__ or ""), FILE)


def _trim(text: str) -> str:
    one = " ".join(text.split())
    return one if len(one) <= LIMIT else one[:LIMIT].rstrip() + " ..."


def entry_of(found: Twinned, seen: date) -> Entry:
    return Entry(found.text, found.twin.dimension, found.values, _trim(found.answers[0]), _trim(found.answers[1]), seen.isoformat())


def load(file: str) -> list[Entry]:
    if not os.path.exists(file):
        return []
    with open(file) as f:
        lines = f.read().splitlines()
    entries: list[Entry] = []
    key = ""
    got: dict[str, str] = {}
    for line in [*lines, "## "]:
        if line.startswith("## "):
            if key:
                entries.append(Entry(key, *(got.get(label, "") for label in LABELS)))
            key, got = line[3:].strip(), {}
        elif line.startswith("- ") and ": " in line:
            label, _, value = line[2:].partition(": ")
            got[label] = value
    return entries


def save(file: str, entries: list[Entry]) -> None:
    lines = [TITLE, "", INTRO, ""]
    for entry in entries:
        lines += [f"## {entry.key}", ""]
        lines += [f"- {label}: {value}" for label, value in zip(LABELS, (entry.dimension, entry.values, entry.first, entry.second, entry.seen))]
        lines.append("")
    with open(file, "w") as f:
        f.write("\n".join(lines))


def settle(tried: Tried, entries: list[Entry], outside: frozenset[str] | None, today: date) -> Settled:
    """Sets `tried.known` to the findings the register holds, or this run adds. `outside` is None where the
    run adds nothing, the empty set where it adds every finding, and else the calls it leaves to the story."""
    settled = Settled()
    held = {e.key for e in entries}
    for found in tried.twins:
        if not found.split:
            continue
        if found.text not in held and outside is not None and found.endpoint.__name__ not in outside:
            settled.fresh.append(entry_of(found, today))
            held.add(found.text)
        if found.text in held:
            settled.known.append(found)
    judged = {t.text for t in tried.twins if t.played or t.distinguished or t.ignored}
    split = {t.text for t in tried.twins if t.split}
    settled.stale = [e for e in entries if e.key in judged and e.key not in split]
    tried.known = settled.known
    return settled
