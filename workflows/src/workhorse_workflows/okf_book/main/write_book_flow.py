"""One turn of a surface's book owner: it holds the whole book, opens on the gates it last failed and writes every page itself, then the run puts back what it changed elsewhere and commits the book."""
from __future__ import annotations

import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from ostler.stamp import stamp_page
from workhorse.pyflow import AgentTimeout, AgentTurnFailed, Await, Continue, Done, WorkflowFailed
from workhorse.runner.failure import OutputParseError
from workhorse_workflows.okf_book.main.nodes.gate import RunFailures
from workhorse_workflows.okf_book.main.nodes.lead_findings import OwnerReply
from workhorse_workflows.okf_book.main.nodes.operator_answer import mark_heard
from workhorse_workflows.okf_book.main.nodes.owner_gate import OWNER_FOLDER, Gates, gate_template_args, record_owner_reply
from workhorse_workflows.okf_book.main.nodes.source_view import turn_folder
from workhorse_workflows.okf_book.main.nodes.surface import Surface
from workhorse_workflows.okf_book.main.nodes.writer_commands import WriterCommandState, write_command_state
from workhorse_workflows.okf_book.main.nodes.writer_jobs import settle_jobs
from workhorse_workflows.okf_book.main.nodes.writer_request import writer_request
from workhorse_workflows.okf_book.shared.blockers import Phase
from workhorse_workflows.okf_book.shared.book_commits import book_commit_subject, unfinished_book_commit_subject
from workhorse_workflows.okf_book.shared.book_flow import BookFlow
from workhorse_workflows.okf_book.shared.book_run import ExerciseResult
from workhorse_workflows.okf_book.shared.confine import Snapshot, book_changes, put_back_outside, snapshot
from workhorse_workflows.okf_book.shared.entries import FEATURES_DIR
from workhorse_workflows.okf_book.shared.metrics import TurnMetric, record_turn, turn_metric
from workhorse_workflows.okf_book.shared.page_check import PageProblem

WRITE_PROMPT = "main/prompts/write-book.md"


def owner_chain(service: str) -> str:
    """The conversation a book's owner keeps across its turns, so each lap resumes where the last one stopped."""
    return f"book:{service}"


class WriteOutcome(BaseModel):
    """What the writer's turn left: whether its book is committed, and why the turn ended without a reply when it is not."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    committed: bool
    failure: str = ""


class WriteBook(BookFlow):
    """Sends one turn of a surface's book owner with the gates it last failed, keeps its writes inside its book, and ends on whether the book was committed."""

    surface: Surface | None = None
    book_folder: str = ""
    source_folder: str = ""
    exercised: ExerciseResult | None = None
    problems: tuple[PageProblem, ...] = ()
    run_failures: RunFailures = {}

    @property
    def surface_to_write(self) -> Surface:
        if self.surface is None:
            raise WorkflowFailed("the write flow names no surface")
        return self.surface

    def _gates(self) -> Gates:
        return Gates(exercised=self.exercised, problems=self.problems, failures=self.run_failures)

    def start(self) -> Continue[...]:
        """Record the tree before the writer runs, so what it changes outside its book can be put back."""
        (self.root / self.book_folder).mkdir(parents=True, exist_ok=True)
        before = snapshot(self.root)
        return Continue(None, self.reset_command_state, before=before).because("give the writer its run allowance")

    def reset_command_state(self, before: Snapshot) -> Continue[...]:
        """Write the command state the writer's three commands read, with none of their runs spent."""
        settle_jobs(self.run_dir)
        command_state_file = write_command_state(self.run_dir, WriterCommandState(root=self.root, service=self.surface_to_write.service, records_dir=self.records_dir))
        return Continue(command_state_file.as_posix(), self.write_book, before=before).because("send the writer")

    def write_book(self, before: Snapshot) -> Continue[...]:
        """One turn, confined to its book folder and to ostler and the two checks, opens on the gates the book last failed and writes the whole book until both pass. The turn resumes the owner's conversation, and a turn that ends without a reply starts the next one fresh. A reply that names no side leaves the gates as they were."""
        surface = self.surface_to_write
        request = writer_request(self.run_dir, self.root, surface, self.book_folder, self.source_folder)
        gate = gate_template_args(self.root, self.records_dir, surface.service, self._gates())
        started = time.monotonic()
        reply = OwnerReply()
        failure: str | None = None
        try:
            reply = self.agent(
                WRITE_PROMPT,
                returns=OwnerReply,
                power="high",
                timeout=float("inf"),
                args={**request.template_args(), **gate},
                cwd=self.root / self.book_folder,
                add_dirs=[request.source_view, turn_folder(self.root, OWNER_FOLDER)],
                profile=request.profile,
                session=owner_chain(surface.service),
            )
        except OutputParseError as unread:
            self.logger.warning("the owner's reply on %s named no side: %s", surface.service, unread)
        except (AgentTurnFailed, AgentTimeout) as failed:
            failure = f"the writer's turn ended without a reply: {failed}"
            self.reset_session(owner_chain(surface.service))
        settle_jobs(self.run_dir)
        node = Path(WRITE_PROMPT).stem
        metric = turn_metric(
            Phase.WRITE, node, (surface.service,), (time.monotonic() - started) / 60, self.turn_usage(node)
        )
        return Continue(reply, self.record_writer_turn, before=before, metric=metric, failure=failure, reply=reply).because(
            "record the writer's turn"
        )

    def record_writer_turn(self, before: Snapshot, metric: TurnMetric, failure: str | None, reply: OwnerReply | None = None) -> Continue[...]:
        """Record what the writer's turn cost, and the side it named of each group of the gates it was shown. A turn that replied has read the operator's answer."""
        record_turn(self.records_dir, metric)
        if reply is not None:
            _ = record_owner_reply(self.records_dir, self.surface_to_write.service, self._gates(), reply)
        if failure is None:
            mark_heard(self.records_dir, self.surface_to_write.service)
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
        return Continue(stray, self.render_agent_files_for_unfinished, before=before, failure=failure).because("render the agent files")

    def render_agent_files_for_unfinished(self, before: Snapshot, failure: str) -> Continue[...] | Await[...]:
        """Render the repo's agent files before the unfinished pages are committed. A failed render waits for the operator."""
        waiting = self._render_agent_files_or_await(self.render_agent_files_for_unfinished, before=before, failure=failure)
        if waiting:
            return waiting
        return Continue(failure, self.commit_unfinished, before=before, failure=failure).because("keep the pages it left")

    def commit_unfinished(self, before: Snapshot, failure: str) -> Done | Await[...]:
        """Commit the pages the failed turn left, under a subject that is not this workflow's, so a rerun sends a writer to finish them.

        A retry after the commit landed finds nothing to commit. A refused commit waits for the operator.
        """
        service = self.surface_to_write.service
        pages = book_changes(self.root, service, before)
        waiting = self._commit_or_await(unfinished_book_commit_subject(service), pages, self.commit_unfinished, before=before, failure=failure)
        if waiting:
            return waiting
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
        pages = tuple(sorted(book_changes(root, self.surface_to_write.service, before)))
        for page in pages:
            if page.endswith(".md") and (root / page).is_file():
                _ = stamp_page(root, root / FEATURES_DIR, page)
        return Continue(pages, self.render_agent_files, pages=pages).because("render the agent files")

    def render_agent_files(self, pages: tuple[str, ...]) -> Continue[...] | Await[...]:
        """Render the repo's agent files before the book is committed. A failed render waits for the operator."""
        waiting = self._render_agent_files_or_await(self.render_agent_files, pages=pages)
        if waiting:
            return waiting
        return Continue(pages, self.commit_book, pages=pages).because("commit the book")

    def commit_book(self, pages: tuple[str, ...]) -> Done | Await[...]:
        """Commit the book's changed pages. A retry after the commit landed finds nothing to commit. A refused commit waits for the operator."""
        waiting = self._commit_or_await(book_commit_subject(self.surface_to_write.service), pages, self.commit_book, pages=pages)
        if waiting:
            return waiting
        return Done(WriteOutcome(committed=True)).because("the book is committed")
