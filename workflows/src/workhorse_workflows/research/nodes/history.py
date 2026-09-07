"""The program's event log: what the loop did, when, to which gate.

`history.jsonl` sits beside the ledger and is written by the loop itself, one JSON line
per event, from the moment this module exists. It is the dossier's source for counts a
prompt would otherwise have to parse out of prose — kills, revivals, apparatus laps,
reviews — and, since the loop writes it, it needs no parser at all going forward.

A program that predates this file gets one *bootstrapped* from its progress file's
dated headings (`source: bootstrap`). Bootstrap is idempotent: it runs only when no
file exists, and every line it writes says where it came from, so a later reader can
weight parsed history below recorded history.

Every write is soft: a history line that cannot be written is logged and dropped,
never a reason to stop a run.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from workhorse_workflows.research.nodes._blueprint import blueprint
from workhorse_workflows.research.schemas import HistoryEvent

HISTORY_NAME = "history.jsonl"

#: The vocabulary. Unknown events are still written; the dossier only counts these.
EVENTS = (
    "gate_selected",
    "pass",
    "fail",
    "kill",
    "apparatus_kill",
    "build_fix",
    "rework",
    "rescope",
    "lead_review",
    "revive",
    "new_direction",
    "program_review",
    "recharter",
    "probe_ordered",
    "cache_directive",
    "goal",
)


def history_path(repo_dir: str, program_dir: str) -> Path:
    return Path(repo_dir) / program_dir / HISTORY_NAME


def read_history(path: Path) -> list[HistoryEvent]:
    """Every line that parses; a malformed line is skipped, not fatal."""
    if not path.is_file():
        return []
    events: list[HistoryEvent] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(HistoryEvent.model_validate(json.loads(line)))
        except (ValueError, TypeError):
            continue
    return events


def write_events(path: Path, events: list[HistoryEvent]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        for event in events:
            fh.write(json.dumps(event.model_dump(mode="json"), sort_keys=True) + "\n")


@blueprint.node
def append_history(
    logger: logging.Logger,
    repo_dir: str,
    program_dir: str,
    event: str,
    gate_id: str = "",
    note: str = "",
    fingerprint: str = "",
    today: str = "",
) -> HistoryEvent:
    """Append one event line. Soft-fails: the run never stops on bookkeeping."""
    record = HistoryEvent(
        date=today or date.today().isoformat(),
        event=event,
        gate_id=gate_id,
        note=note[:500],
        source="loop",
        fingerprint=fingerprint,
    )
    try:
        write_events(history_path(repo_dir, program_dir), [record])
    except OSError as exc:  # pragma: no cover - disk trouble is logged, not raised
        logger.warning("history %s not written: %s", event, exc)
    return record


def bootstrap_history(path: Path, events: list[HistoryEvent]) -> bool:
    """Seed a missing history file from parsed prose. Returns whether it wrote.

    Idempotent by construction: an existing file, even an empty one, is left alone.
    """
    if path.exists():
        return False
    stamped = [e.model_copy(update={"source": "bootstrap"}) for e in events]
    try:
        write_events(path, stamped)
    except OSError:
        return False
    return True


__all__ = [
    "EVENTS",
    "HISTORY_NAME",
    "append_history",
    "bootstrap_history",
    "history_path",
    "read_history",
    "write_events",
]
