"""The lines the run ends on, one record each: a line per book, and for a book moved onto the format a line per batch, per kind of note and for what remains."""
from __future__ import annotations

import math

from workhorse_workflows.okf_book.catch_up.models import BatchOutcome, BookOutcome


def _many(count: int, word: str, plural: str = "") -> str:
    return f"{count} {word}" if count == 1 else f"{count} {plural or word + 's'}"


def batch_line(batch: BatchOutcome) -> str:
    """What one committed batch asked, got, played and took."""
    played = [_many(batch.calls, "call")] * bool(batch.calls) + [_many(batch.journeys, "journey", "journeys")] * bool(batch.journeys)
    plays = f"played {' and '.join(played)} {'green' if batch.exit_code in (0, None) else f'exit {batch.exit_code}'}" if played else "played nothing"
    return f"batch {batch.number}: {batch.asked} asked, {batch.done} done, {batch.outside} outside, {_many(batch.laps, 'lap')}, {round(batch.minutes)} min, {plays}, committed"


def outcome_lines(outcome: BookOutcome) -> list[str]:
    """The lines of one book's outcome."""
    if outcome.move is None:
        return [_line(outcome)]
    service = outcome.service
    owed = [f"{service}: owed to a scheduled whole play: {outcome.move.owed}"] if outcome.move.owed else []
    return [*_head(outcome), *(f"{service}: {batch_line(batch)}" for batch in outcome.batches), *(f"{service}: {kind.said}" for kind in outcome.move.kinds), *owed, *_remains(outcome)]


def _remains(outcome: BookOutcome) -> list[str]:
    if not outcome.remaining:
        return []
    more = math.ceil(outcome.remaining / max(outcome.batch_notes, 1))
    left = f"{outcome.remaining} note remains" if outcome.remaining == 1 else f"{outcome.remaining} notes remain"
    return [f"{outcome.service}: {left}: run catch_up again, about {_many(more, 'batch', 'batches')}"]


def _head(outcome: BookOutcome) -> list[str]:
    if outcome.app:
        return [f"{_caught_up(outcome)}{_applied(outcome)}"]
    if outcome.format:
        return [f"{outcome.service}: moved onto the format{_applied(outcome)}"]
    return []


def _applied(outcome: BookOutcome) -> str:
    return f", {_count(outcome, 'applied')} changes applied, {_count(outcome, 'not applicable')} not applicable" if outcome.format else ""


def _line(outcome: BookOutcome) -> str:
    if outcome.verdict == "current":
        return f"{outcome.service}: current"
    if outcome.verdict == "first-book":
        return f"{outcome.service}: first book, write it with python_book"
    moved = f"moved onto the format, {_count(outcome, 'applied')} changes applied, {_count(outcome, 'not applicable')} not applicable"
    if not outcome.app:
        return f"{outcome.service}: {moved}"
    line = _caught_up(outcome)
    return f"{line}, {moved}" if outcome.moved else line


def _caught_up(outcome: BookOutcome) -> str:
    line = f"{outcome.service}: caught up in {outcome.laps} laps, {len(outcome.elements)} elements changed, {len(outcome.added)} endpoints added"
    if outcome.ignored:
        line += f", {len(outcome.ignored)} files ignored: {', '.join(outcome.ignored)}"
    return line


def _count(outcome: BookOutcome, kind: str) -> int:
    return sum(1 for line in outcome.format if line.partition(" ")[2].startswith(kind))
