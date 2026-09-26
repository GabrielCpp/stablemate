"""One surface's writer turn: it writes the whole book in its folder, then the run puts back what it changed elsewhere and commits the book."""
from __future__ import annotations

import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from ostler.stamp import stamp_page
from workhorse.pyflow import AgentTimeout, AgentTurnFailed, Continue, Done, WorkflowFailed
from workhorse_workflows.kit import commit_paths
from workhorse_workflows.okf_book.main.nodes.surface import Surface
from workhorse_workflows.okf_book.main.nodes.writer_commands import WriterCommandState, write_command_state
from workhorse_workflows.okf_book.main.nodes.writer_request import writer_request
from workhorse_workflows.okf_book.shared.blockers import Phase
from workhorse_workflows.okf_book.shared.book_commits import book_commit_subject, unfinished_book_commit_subject
from workhorse_workflows.okf_book.shared.book_flow import BookFlow
from workhorse_workflows.okf_book.shared.confine import Snapshot, book_changes, put_back_outside, snapshot
from workhorse_workflows.okf_book.shared.entries import FEATURES_DIR
from workhorse_workflows.okf_book.shared.metrics import TurnMetric, record_turn

WRITE_PROMPT = "main/prompts/write-book.md"


class WriteOutcome(BaseModel):
    """What the writer's turn left: whether its book is committed, and why the turn ended without a reply when it is not."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    committed: bool
    failure: str = ""


class WriteBook(BookFlow):
    """Sends one surface's writer, keeps its writes inside its book, and ends on whether the book was committed."""

    surface: Surface | None = None
    book_folder: str = ""
    source_folder: str = ""
    source_view: str = ""

    @property
    def surface_to_write(self) -> Surface:
        if self.surface is None:
            raise WorkflowFailed("the write flow names no surface")
        return self.surface

    def start(self) -> Continue[...]:
        """Record the tree before the writer runs, so what it changes outside its book can be put back."""
        (self.root / self.book_folder).mkdir(parents=True, exist_ok=True)
        before = snapshot(self.root)
        return Continue(None, self.reset_command_state, before=before).because("give the writer its run allowance")

    def reset_command_state(self, before: Snapshot) -> Continue[...]:
        """Write the command state the writer's three commands read, with none of their runs spent."""
        command_state_file = write_command_state(self.run_dir, WriterCommandState(root=self.root, service=self.surface_to_write.service))
        return Continue(command_state_file.as_posix(), self.write_book, before=before).because("send the writer")

    def write_book(self, before: Snapshot) -> Continue[...]:
        """One turn, confined to its book folder and to ostler and the two checks, writes the whole book until both pass."""
        surface = self.surface_to_write
        request = writer_request(self.run_dir, surface, self.book_folder, self.source_folder, Path(self.source_view))
        started = time.monotonic()
        reply = ""
        failure: str | None = None
        try:
            reply = self.agent(
                WRITE_PROMPT,
                returns=str,
                power="medium",
                timeout=float("inf"),
                args=request.template_args(),
                cwd=self.root / self.book_folder,
                add_dirs=[request.source_view],
                profile=request.profile,
            )
        except (AgentTurnFailed, AgentTimeout) as failed:
            failure = f"the writer's turn ended without a reply: {failed}"
        metric = TurnMetric(
            phase=Phase.WRITE,
            node=Path(WRITE_PROMPT).stem,
            subjects=(surface.service,),
            minutes=(time.monotonic() - started) / 60,
        )
        return Continue(reply, self.record_writer_turn, before=before, metric=metric, failure=failure).because(
            "record the writer's turn"
        )

    def record_writer_turn(self, before: Snapshot, metric: TurnMetric, failure: str | None) -> Continue[...]:
        """Record what the writer's turn cost."""
        record_turn(self.records_dir, metric)
        if failure is not None:
            return Continue(failure, self.put_back_after_failed_turn, before=before, failure=failure).because(
                "the writer's turn failed"
            )
        return Continue(metric, self.put_back, before=before).because("put back writes outside the book")

    def put_back_after_failed_turn(self, before: Snapshot, failure: str) -> Continue[...]:
        """Put back what the failed writer turn changed outside its book."""
        stray = put_back_outside(self.root, self.surface_to_write.service, before, self.run_dir)
        for path in stray:
            self.logger.warning("put back %s, which the failed writer turn changed outside its book", path)
        return Continue(stray, self.commit_unfinished, before=before, failure=failure).because("keep the pages it left")

    def commit_unfinished(self, before: Snapshot, failure: str) -> Done:
        """Commit the pages the failed turn left, under a subject that is not this workflow's, so a rerun sends a writer to finish them.

        A retry after the commit landed finds nothing to commit.
        """
        service = self.surface_to_write.service
        pages = book_changes(self.root, service, before)
        _ = commit_paths(self.root, unfinished_book_commit_subject(service), *pages)
        return Done(WriteOutcome(committed=False, failure=failure)).because("the writer's turn failed")

    def put_back(self, before: Snapshot) -> Continue[...]:
        """Put back what the writer changed outside its book."""
        stray = put_back_outside(self.root, self.surface_to_write.service, before, self.run_dir)
        for path in stray:
            self.logger.warning("put back %s, which the writer changed outside its book", path)
        return Continue(stray, self.stamp_book, before=before).because("stamp the book's pages")

    def stamp_book(self, before: Snapshot) -> Continue[...]:
        """Stamp every page the writer changed in its book."""
        root = self.root
        pages = book_changes(root, self.surface_to_write.service, before)
        for page in pages:
            if page.endswith(".md") and (root / page).is_file():
                _ = stamp_page(root, root / FEATURES_DIR, page)
        return Continue(pages, self.commit_book, pages=pages).because("commit the book")

    def commit_book(self, pages: tuple[str, ...]) -> Done:
        """Commit the book's changed pages. A retry after the commit landed finds nothing to commit."""
        _ = commit_paths(self.root, book_commit_subject(self.surface_to_write.service), *pages)
        return Done(WriteOutcome(committed=True)).because("the book is committed")
