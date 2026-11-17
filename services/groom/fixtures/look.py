"""What an operator or a program sends to read one run, one container's files, the attendant's
log or a dispatch queue. One fixture carries every path part and query field these calls
take, so a step names the thing it looks at once."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from ostler.book import Actor, Fixture

from .push import _next_name


@dataclass(eq=False)
class Look(Fixture):
    run_id: str | None = None
    container_id: str | None = None
    key: str | None = None
    slug: str | None = None
    q: str | None = None
    before: str | None = None
    limit: int | None = None
    metrics: int | None = None
    logs: int | None = None
    archives: int | None = None
    include_all: bool | None = None
    repo: str | None = None
    path: str | None = None
    view: str | None = None
    file_path: str | None = None
    answer: str | None = None
    body: str | None = None
    run: str | None = None
    session_id: str | None = None
    job_id: str | None = None
    queue: str | None = None
    item_id: str | None = None

    def __str__(self) -> str:
        return self.run_id or self.container_id or self.queue or self.session_id or self.job_id or "(nothing)"

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[Look]:
        known = (looking_at(run.container_id) for run in state.runs)
        return (*known, looking_at(_next_name()))


def looking_at(run: str | None = None, **fields: Any) -> Look:
    """One run, addressed the way each call names it: by run id, and by container id."""
    ident = run or _next_name()
    return Look(run_id=ident, container_id=ident, session_id=ident, job_id=ident, queue=ident, item_id=ident, **fields)


def asking(**fields: Any) -> Look:
    """A read that names no run: the fields alone."""
    return Look(**fields)
