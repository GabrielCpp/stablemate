"""The sandbox the loop runner works in: the watched files it holds, and the
questions the commands ask of them."""

from __future__ import annotations

from typing import cast

from ostler.book import Collection, State, Unique

from ..fixtures import FINISHED, PARKED
from .files import (ELSEWHERE, M1_ANSWERED, M1_OPEN, M2_ANSWERED, M2_YES, REWOUND, RUNS, STALE, TERMINAL, FileRecord, at,
                    run_dir)

DRY_RUN = "dry-run"
PREFIX = f"{RUNS}/loop-runner-"


class Runs(State):
    files = Collection(FileRecord, Unique("path"))

    def rows(self) -> tuple[FileRecord, ...]:
        return tuple(sorted(self.files, key=lambda f: f.path))

    def row(self, entity: object) -> FileRecord:
        return cast(FileRecord, entity)


def holds(s: Runs, name: str, file: str) -> tuple[str, ...]:
    """The strings a file of a run in the default runs directory holds; none when the file is not there."""
    record = s.files.get(at(name, file))
    return record.holds if record is not None else ()


def exists(s: Runs, name: str) -> bool:
    """Whether the default runs directory holds a run of this name."""
    return at(name, "run.json") in s.files


def finished(s: Runs, name: str) -> bool:
    return TERMINAL in holds(s, name, "run.json")


def unfinished(s: Runs) -> str | None:
    """The run `--run` leaves out means: the newest run of the default runs directory that has not finished."""
    names = sorted(
        f.path.removeprefix(PREFIX).removesuffix("/run.json")
        for f in s.files
        if f.path.startswith(PREFIX) and f.path.endswith("/run.json") and TERMINAL not in f.holds
    )
    return names[-1] if names else None


def held_params(s: Runs, name: str) -> tuple[str, ...]:
    """The params the run's checkpoint carries."""
    return ("stale",) if STALE in holds(s, name, "checkpoint.json") else ()


def messages(s: Runs, name: str) -> tuple[tuple[str, str, str, str], ...]:
    """The inbox of a run as (id, body, reply, at) rows; the reply is empty while the message is outstanding."""
    held = holds(s, name, "inbox.jsonl")
    rows = []
    if M1_OPEN in held:
        rows.append(("m1", "Which branch should I use?", "", "2026-11-01T10:00:00+00:00"))
    if M1_ANSWERED in held:
        rows.append(("m1", "Which branch should I use?", "go ahead", "2026-11-01T10:00:00+00:00"))
    if M2_YES in held:
        rows.append(("m2", "Is the plan approved?", "yes", "2026-11-01T11:00:00+00:00"))
    if M2_ANSWERED in held:
        rows.append(("m2", "Is the plan approved?", "go ahead", "2026-11-01T11:00:00+00:00"))
    return tuple(rows)


def stage(model: Runs) -> str:
    """How far the sandbox has come: the scene it is in."""
    files = model.files
    words: list[str] = []
    if at(PARKED, "checkpoint.json") in files:
        words.append("rewound" if REWOUND in holds(model, PARKED, "events.jsonl") else "parked")
        if M1_ANSWERED in holds(model, PARKED, "inbox.jsonl"):
            words.append("replied")
        if M2_ANSWERED in holds(model, PARKED, "inbox.jsonl"):
            words.append("approved")
    if at(FINISHED, "run.json") in files:
        words.append("finished")
    if f"{run_dir(DRY_RUN)}/run.json" in files:
        words.append(DRY_RUN)
    if f"{run_dir(DRY_RUN, ELSEWHERE)}/run.json" in files:
        words.append("dry-run elsewhere")
    if any(f.path.endswith(".dot") for f in files):
        words.append("drawn")
    return " + ".join(words) if words else "empty"


__all__ = ["DRY_RUN", "Runs", "exists", "finished", "held_params", "holds", "messages", "stage", "unfinished"]
