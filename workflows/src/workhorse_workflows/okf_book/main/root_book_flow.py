"""The root of a book: code writes and commits the entries page of a book HEAD holds none for, so every check can tell what it reaches."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from workhorse.pyflow import Await, Continue, Done
from workhorse_workflows.okf_book.main.nodes.root_entries import write_root_entries
from workhorse_workflows.okf_book.shared.book_commits import rooted_book_commit_subject
from workhorse_workflows.okf_book.shared.book_flow import BookFlow
from workhorse_workflows.okf_book.shared.confine import absent_from_head, in_book, snapshot
from workhorse_workflows.okf_book.shared.entries import entries_path


class RootedBook(BaseModel):
    """What the root leaves for the repair: the book pages someone left uncommitted before it began."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    uncommitted_at_start: tuple[str, ...] = ()


class RootBook(BookFlow):
    """Records the book pages someone left uncommitted, then roots the book."""

    service: str = ""

    def start(self) -> Continue[...]:
        """Record the book pages someone left uncommitted, so no turn is sent them and no commit takes them."""
        uncommitted_at_start = tuple(sorted(path for path in snapshot(self.root).digests if in_book(self.service, path)))
        return Continue(uncommitted_at_start, self.root_book, uncommitted_at_start=uncommitted_at_start).because("root the book")

    def root_book(self, uncommitted_at_start: tuple[str, ...]) -> Continue[...] | Done:
        """Write and commit the entries page of a book HEAD holds none for.

        A page someone left uncommitted roots the book as it is. One an earlier try of this state wrote is still committed here, since no later state commits it.
        """
        path = entries_path(self.root, self.service)
        page = path.relative_to(self.root).as_posix()
        if page not in absent_from_head(self.root, (page,)) or page in uncommitted_at_start:
            return Done(RootedBook(uncommitted_at_start=uncommitted_at_start)).because("the book has its root")
        if not path.is_file():
            page = write_root_entries(self.root, self.service)
        return Continue(page, self.commit_root, uncommitted_at_start=uncommitted_at_start, page=page).because("commit the entries page")

    def commit_root(self, uncommitted_at_start: tuple[str, ...], page: str) -> Done | Await[...]:
        """Commit the entries page. A refused commit waits for the operator."""
        refusal = self._commit(rooted_book_commit_subject(self.service), page)
        if refusal:
            return self._await_operator_on_refused_commit(refusal, self.commit_root, uncommitted_at_start=uncommitted_at_start, page=page)
        return Done(RootedBook(uncommitted_at_start=uncommitted_at_start)).because("the book is rooted")
