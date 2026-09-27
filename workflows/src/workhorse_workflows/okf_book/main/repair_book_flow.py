"""The repair of a book: code roots it, then one confined turn per batch of problem pages fixes them, round after round.

A book goes to its repair when it is too large for one writer, or when a book this workflow wrote
failed its run. The run's failures are the first round's problems on the pages they cover.

A page someone left uncommitted when the repair started is never sent to a turn and never committed,
so their edits stay theirs.
"""
from __future__ import annotations

import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from ostler.stamp import stamp_page
from workhorse.pyflow import AgentTimeout, AgentTurnFailed, Await, Continue, Done, WorkflowFailed
from workhorse_workflows.kit import commit_or_refusal
from workhorse_workflows.okf_book.main.nodes.repair_batches import RepairBatch, problems_by_page, repair_batches
from workhorse_workflows.okf_book.main.nodes.root_entries import write_root_entries
from workhorse_workflows.okf_book.main.nodes.surface import Surface
from workhorse_workflows.okf_book.main.nodes.writer_commands import WriterCommandState, write_command_state
from workhorse_workflows.okf_book.main.nodes.writer_request import writer_request
from workhorse_workflows.okf_book.shared.blockers import Phase
from workhorse_workflows.okf_book.shared.book_commits import repaired_book_commit_subject, rooted_book_commit_subject
from workhorse_workflows.okf_book.shared.book_flow import BookFlow
from workhorse_workflows.okf_book.shared.confine import Snapshot, book_changes, in_book, put_back_outside, restore, snapshot
from workhorse_workflows.okf_book.shared.entries import FEATURES_DIR, entries_path
from workhorse_workflows.okf_book.shared.metrics import record_turn, turn_metric
from workhorse_workflows.okf_book.shared.page_check import PageProblem, page_problems

REPAIR_PROMPT = "main/prompts/repair-pages.md"
REPAIR_ROUNDS = 3


class RepairOutcome(BaseModel):
    """What the repair left: the rounds it ran, the turns that ended without a reply, and how many problems remain."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rounds: int
    failed_turns: tuple[str, ...] = ()
    problems_left: int = 0


class RepairRound(BaseModel):
    """One round of the repair: the pages no turn may touch, its number, the turns that failed so far, and its batches."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    held: tuple[str, ...]
    number: int
    failed: tuple[str, ...]
    batches: tuple[RepairBatch, ...]


class RepairBook(BookFlow):
    """Roots the book, then sends one repair turn per batch of problem pages until the check is clean or the rounds are spent."""

    surface: Surface | None = None
    book_folder: str = ""
    source_folder: str = ""
    run_failures: dict[str, tuple[str, ...]] = {}

    @property
    def surface_to_repair(self) -> Surface:
        if self.surface is None:
            raise WorkflowFailed("the repair flow names no surface")
        return self.surface

    @property
    def service(self) -> str:
        return self.surface_to_repair.service

    def start(self) -> Continue[...]:
        """Record the book pages someone left uncommitted, so no turn is sent them and no commit takes them."""
        held = tuple(sorted(path for path in snapshot(self.root).digests if in_book(self.service, path)))
        return Continue(held, self.root_book, held=held).because("root the book")

    def root_book(self, held: tuple[str, ...]) -> Continue[...]:
        """Write and commit the entries page of a book that has none, so every check can tell what it reaches."""
        if entries_path(self.root, self.service).is_file():
            return Continue(None, self.plan_round, held=held, round_number=1, failed=()).because("the book has its root")
        page = write_root_entries(self.root, self.service)
        return Continue(page, self.commit_root, held=held, page=page).because("commit the entries page")

    def commit_root(self, held: tuple[str, ...], page: str) -> Continue[...] | Await[...]:
        """Commit the entries page. A refused commit waits for the operator."""
        refusal = commit_or_refusal(self.root, rooted_book_commit_subject(self.service), page)
        if refusal:
            return self._commit_refused(refusal, self.commit_root, held=held, page=page)
        return Continue(page, self.plan_round, held=held, round_number=1, failed=()).because("the book is rooted")

    def plan_round(self, held: tuple[str, ...], round_number: int, failed: tuple[str, ...]) -> Continue[...] | Done:
        """Check the book and pack its problem pages into batches. A clean book, or one the rounds are spent on, ends the repair."""
        run_problems = [PageProblem(page, text) for page, texts in self.run_failures.items() for text in texts] if round_number == 1 else []
        by_page = problems_by_page((*page_problems(self.root, self.service), *run_problems), frozenset(held))
        left = sum(len(problems) for problems in by_page.values())
        outcome = RepairOutcome(rounds=round_number - 1, failed_turns=failed, problems_left=left)
        if not by_page:
            return Done(outcome).because("the book is clean")
        if round_number > REPAIR_ROUNDS:
            return Done(outcome).because("the repair rounds are spent")
        batches = repair_batches(self.root, by_page)
        self.logger.info("round %d repairs %d pages with %d problems in %d turns", round_number, len(by_page), left, len(batches))
        repair = RepairRound(held=held, number=round_number, failed=failed, batches=batches)
        return Continue(len(batches), self.repair_batch, repair=repair, index=0).because("repair the first batch")

    def repair_batch(self, repair: RepairRound, index: int) -> Continue[...]:
        """One turn, confined to the book folder and to ostler, the scoped check and the scenario run, repairs one batch of pages."""
        batch = repair.batches[index]
        before = snapshot(self.root)
        known = tuple(problem.text for problem in page_problems(self.root, self.service))
        state = WriterCommandState(root=self.root, service=self.service, pages=batch.page_paths, before=before, known=known)
        _ = write_command_state(self.run_dir, state)
        request = writer_request(self.run_dir, self.root, self.surface_to_repair, self.book_folder, self.source_folder)
        started = time.monotonic()
        failure = ""
        try:
            _ = self.agent(
                REPAIR_PROMPT,
                returns=str,
                power="medium",
                timeout=float("inf"),
                args=request.repair_template_args(batch, failed_run=bool(self.run_failures)),
                cwd=self.root / self.book_folder,
                add_dirs=[request.source_view],
                profile=request.repair_profile,
            )
        except (AgentTurnFailed, AgentTimeout) as ended:
            failure = f"the repair turn on {', '.join(batch.page_paths)} ended without a reply: {ended}"
        node = Path(REPAIR_PROMPT).stem
        metric = turn_metric(Phase.WRITE, node, (self.service,), (time.monotonic() - started) / 60, self.turn_usage(node))
        record_turn(self.records_dir, metric)
        if failure:
            self.logger.warning("%s", failure)
            repair = repair.model_copy(update={"failed": (*repair.failed, failure)})
        return Continue(failure, self.commit_batch, repair=repair, index=index, before=before).because("commit what the turn changed")

    def commit_batch(self, repair: RepairRound, index: int, before: Snapshot) -> Continue[...]:
        """Put back what the turn changed outside the book and on the entries page, and stamp the rest."""
        root = self.root
        stray = put_back_outside(root, self.service, before, self.run_dir)
        for path in stray:
            self.logger.warning("put back %s, which the repair turn changed outside its book", path)
        entries = entries_path(root, self.service).relative_to(root).as_posix()
        changed = book_changes(root, self.service, before)
        _ = restore(root, [path for path in changed if path == entries], before)
        pages = tuple(path for path in changed if path != entries and path not in repair.held and path not in before.digests)
        for page in pages:
            if page.endswith(".md") and (root / page).is_file():
                _ = stamp_page(root, root / FEATURES_DIR, page)
        return Continue(pages, self.commit_pages, repair=repair, index=index, pages=pages).because("commit the repaired pages")

    def commit_pages(self, repair: RepairRound, index: int, pages: tuple[str, ...]) -> Continue[...] | Await[...]:
        """Commit the batch's pages and move to the next batch. A refused commit waits for the operator."""
        refusal = commit_or_refusal(self.root, repaired_book_commit_subject(self.service), *pages)
        if refusal:
            return self._commit_refused(refusal, self.commit_pages, repair=repair, index=index, pages=pages)
        if index + 1 < len(repair.batches):
            return Continue(pages, self.repair_batch, repair=repair, index=index + 1).because("repair the next batch")
        return Continue(pages, self.plan_round, held=repair.held, round_number=repair.number + 1, failed=repair.failed).because(
            "check the book again"
        )
