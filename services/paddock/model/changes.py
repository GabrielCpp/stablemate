"""The changes a round makes to the root: the notes its steps write and the round it leaves."""

from __future__ import annotations

from ostler.book import Create, Transaction, Update

from ..fixtures import RunArgs, RunStepArgs
from .files import FileRecord
from .rounds import Played, Round, Task, ledger_of, play, score_of, task_named
from .state import Root, rounds_of


def write(s: Root, path: str, *strings: str) -> Create | Update:
    """The change that leaves this file holding exactly these strings."""
    record = FileRecord.holding(path, *strings)
    return Update(s.files, path, record) if path in s.files else Create(s.files, record)


def settle(s: Root, task: Task, played: Played, pinned: bool, number: int, earlier: tuple[str, ...] = ()) -> Transaction:
    """What a round that ran its steps leaves behind: the notes, and its round, open when a step stopped it."""
    changes: list[Create | Update] = [write(s, path, *lines) for path, lines in dict(played.writes).items()]
    key = f"{task.name}/{number}"
    done = tuple(name for name, status in played.outcomes if status == "ok")
    if played.interrupted:
        record = Round(key, task.name, number, True, done, pinned, ("interrupted",))
    else:
        segments = (*earlier, "finished")
        record = Round(key, task.name, number, False, done, pinned, segments,
                       ledger_of(task, played, pinned, segments), score_of(task))
    changes.append(Update(s.rounds, key, record) if key in s.rounds else Create(s.rounds, record))
    return Transaction(*changes, says=played.lines)


def start(s: Root, a: RunArgs | RunStepArgs) -> Transaction:
    """A new round of the task the request names, with the next free number."""
    task = task_named(a.task)
    assert task is not None
    pinned = not a.no_pin_project
    number = 1 + max((r.n for r in rounds_of(s, task.name)), default=0)
    return settle(s, task, play(s, task, pinned), pinned, number)
