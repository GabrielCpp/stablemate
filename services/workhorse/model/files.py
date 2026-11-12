"""The files the book watches and what the model keeps for each: its path and
which of the declared strings it holds. A row is that and nothing more."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import ClassVar

from ostler.book import Mark

RUNS = ".agents/runs"
ELSEWHERE = "elsewhere"
ROOTS = (RUNS, ELSEWHERE)

FLOW = '"flow": "LoopRunner"'
GATE = '"waiting_on": "gate"'
FREE = '"waiting_on": null'
STALE = '"stale": 1'
TERMINAL = '"terminal": "terminal"'
REWOUND = '"phase":"rewind"'

QUESTION = '"id":"m1","body":"Which branch should I use?","at":"2026-11-01T10:00:00+00:00",'
APPROVAL = '"id":"m2","body":"Is the plan approved?","at":"2026-11-01T11:00:00+00:00",'
M1_OPEN = QUESTION + '"reply":"",'
M1_ANSWERED = QUESTION + '"reply":"go ahead",'
M2_YES = APPROVAL + '"reply":"yes",'
M2_ANSWERED = APPROVAL + '"reply":"go ahead",'

GRAPH_LOOP_RUNNER = "digraph loop_runner {"
GRAPH_CHART = "digraph chart {"


def run_dir(name: str, root: str = RUNS) -> str:
    """The directory of the loop runner's run of this name, relative to the sandbox."""
    return f"{root}/loop-runner-{name}"


def at(name: str, file: str, root: str = RUNS) -> str:
    return f"{run_dir(name, root)}/{file}"


MARKS = (
    *(Mark(f"{root}/*/checkpoint.json", FLOW, GATE, FREE, STALE) for root in ROOTS),
    *(Mark(f"{root}/*/run.json", TERMINAL) for root in ROOTS),
    *(Mark(f"{root}/*/events.jsonl", REWOUND) for root in ROOTS),
    Mark(f"{RUNS}/*/inbox.jsonl", M1_OPEN, M1_ANSWERED, M2_YES, M2_ANSWERED),
    Mark("*.dot", GRAPH_LOOP_RUNNER, GRAPH_CHART),
)


@dataclass(frozen=True)
class FileRecord:
    """A watched file the sandbox holds."""

    path: str
    holds: tuple[str, ...] = ()

    source: ClassVar[tuple[str, ...]] = (
        "workhorse/workhorse/rewind.py::rewind",
        "workhorse/workhorse/inbox.py::reply",
    )

    def __str__(self) -> str:
        return f"{self.path} [{'; '.join(self.holds)}]"


def declared(path: str) -> tuple[str, ...]:
    """The strings the watch looks for in this path, in the order it lists them."""
    return tuple(dict.fromkeys(s for m in MARKS if fnmatch.fnmatchcase(path, m.glob) for s in m.holds))


def holding(path: str, *strings: str) -> FileRecord:
    """The record of a file that holds these strings, in the order the watch lists them."""
    return FileRecord(path, tuple(s for s in declared(path) if s in strings))
