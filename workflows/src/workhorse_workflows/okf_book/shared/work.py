"""The run's work list: every file, orphan and aggregation job it covers, and how far each got.

Each list is seeded once, the first time its phase reaches it, so a resume walks the same rows in the same order.
"""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from workhorse.worklist import JsonBackend, WorkItem, WorkList

WORKLIST_NAME = "worklist.json"
FILE = "file"
ORPHAN = "orphan"
JOB = "job"
UNQUEUED = "unqueued"
SEEDED = "seeded"
DONE = "done"
BLOCKED = "blocked"


def book_work(records_dir: Path) -> WorkList:
    return WorkList(JsonBackend(records_dir / WORKLIST_NAME))


def seed(work: WorkList, kind: str, rows: Iterable[WorkItem]) -> None:
    """Add the rows of `kind` once. A list already seeded keeps its rows, even none, and `rows` is never read."""
    stored = work.backend.load()
    if any(item.kind == SEEDED and item.id == kind for item in stored):
        return
    marker = WorkItem(id=kind, kind=SEEDED, status=DONE)
    work.backend.save([*stored, *rows, marker])


def ids(work: WorkList, kind: str, status: str | None = None) -> tuple[str, ...]:
    """The ids of `kind` in order, or only those at `status`."""
    rows = sorted(work.items(kind), key=lambda item: item.order if item.order is not None else 0)
    return tuple(item.id for item in rows if status is None or item.status == status)
