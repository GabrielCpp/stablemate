"""The root of a book: code writes and commits the entries page of a book HEAD holds none for, so every check can tell what it reaches."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from workhorse.pyflow import Await, Continue, Done
from workhorse_workflows.okf_book.main.nodes.root_entries import entry_links, write_root_entries
from workhorse_workflows.okf_book.shared.book_commits import rooted_book_commit_subject
from workhorse_workflows.okf_book.shared.book_flow import BookFlow
from workhorse_workflows.okf_book.shared.confine import absent_from_head, in_book, snapshot
from workhorse_workflows.okf_book.shared.entries import entries_path, read_entries


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
        """Write and commit the entries page of a book HEAD holds none for, or holds one that links nothing while the book has an entry page.

        A page someone left uncommitted roots the book as it is. One an earlier try of this state wrote is still committed here, since no later state commits it. A committed page that links nothing was written before the book had an entry page, and no turn may change it, so code writes it again once there is a page to link.
        """
        path = entries_path(self.root, self.service)
        page = path.relative_to(self.root).as_posix()
        committed = page not in absent_from_head(self.root, (page,))
        if page in uncommitted_at_start:
            return Done(RootedBook(uncommitted_at_start=uncommitted_at_start)).because("the book has its root")
        if committed and (read_entries(self.root, self.service) or not entry_links(self.root, self.service)):
            return Done(RootedBook(uncommitted_at_start=uncommitted_at_start)).because("the book has its root")
        if committed or not path.is_file():
            page = write_root_entries(self.root, self.service)
        return Continue(page, self.render_agent_files, uncommitted_at_start=uncommitted_at_start, page=page).because("render the agent files")

    def render_agent_files(self, uncommitted_at_start: tuple[str, ...], page: str) -> Continue[...] | Await[...]:
        """Render the repo's agent files before the entries page is committed. A failed render waits for the operator."""
        waiting = self._render_agent_files_or_await(self.render_agent_files, uncommitted_at_start=uncommitted_at_start, page=page)
        if waiting:
            return waiting
        return Continue(page, self.commit_root, uncommitted_at_start=uncommitted_at_start, page=page).because("commit the entries page")

    def commit_root(self, uncommitted_at_start: tuple[str, ...], page: str) -> Done | Await[...]:
        """Commit the entries page. A refused commit waits for the operator."""
        waiting = self._commit_or_await(rooted_book_commit_subject(self.service), (page,), self.commit_root, uncommitted_at_start=uncommitted_at_start, page=page)
        if waiting:
            return waiting
        return Done(RootedBook(uncommitted_at_start=uncommitted_at_start)).because("the book is rooted")
