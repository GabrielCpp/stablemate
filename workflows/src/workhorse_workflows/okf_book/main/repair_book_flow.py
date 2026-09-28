"""The repair of a book: once its root is committed, one confined turn per batch of problem pages fixes them, round after round.

A book goes to its repair when it is too large for one writer. When the book failed its run, the
run's failures are the first round's problems on the pages they cover.

The first round fixes the pages the repair works on. A later round repairs what is left on those
pages, and a problem found on any other page is left for the book check to report. A page the check
found clean after its batch is closed: code puts it back when a later turn changes it, and a problem
it has later is left for the book check, so no turn repairs it twice. An entry page closes only
after the round's last batch that may add link lines to it. A page too large for one writer is sent to no turn and
reported.

Code puts back each page a turn changed that its batch may not keep, by the rules of `nodes/repair_put_back.py`.

A page someone left uncommitted when the repair started is never sent to a turn and never committed,
so their edits stay theirs. A turn that changed one waits for the operator.
"""
from __future__ import annotations

import time
from pathlib import Path

from workhorse.pyflow import AgentTimeout, AgentTurnFailed, Await, Continue, Done, WorkflowFailed
from workhorse_workflows.kit import commit_returning_refusal
from workhorse_workflows.okf_book.main.nodes.journey import journey_pages, pages_needing_journey
from workhorse_workflows.okf_book.main.nodes.repair_batches import pack_repairs, problems_by_page
from workhorse_workflows.okf_book.main.nodes.repair_ledger import RepairLedger, RepairRound
from workhorse_workflows.okf_book.main.nodes.repair_put_back import (
    entry_pages_changed_beyond_links,
    pages_to_stamp,
    stamp_repaired_pages,
    turn_changes,
)
from workhorse_workflows.okf_book.main.nodes.surface import Surface
from workhorse_workflows.okf_book.main.nodes.writer_commands import WriterCommandState, write_command_state
from workhorse_workflows.okf_book.main.nodes.writer_request import writer_request
from workhorse_workflows.okf_book.main.root_book_flow import RootBook, RootedBook
from workhorse_workflows.okf_book.shared.blockers import Phase
from workhorse_workflows.okf_book.shared.book_commits import repaired_book_commit_subject
from workhorse_workflows.okf_book.shared.book_flow import BookFlow
from workhorse_workflows.okf_book.shared.confine import Snapshot, put_back_outside, restore, snapshot
from workhorse_workflows.okf_book.shared.metrics import TurnMetric, record_turn, turn_metric
from workhorse_workflows.okf_book.shared.page_check import PageProblem, page_problems

REPAIR_PROMPT = "main/prompts/repair-pages.md"
REPAIR_ROUNDS = 3
UNCOMMITTED_PAGE_GATE = "uncommitted-page-changed.md"


class RepairBook(BookFlow):
    """Has the book rooted, then sends one repair turn per batch of problem pages until the check is clean or the rounds are spent."""

    surface: Surface | None = None
    book_folder: str = ""
    source_folder: str = ""
    run_failures: dict[str, tuple[PageProblem, ...]] = {}

    @property
    def surface_to_repair(self) -> Surface:
        if self.surface is None:
            raise WorkflowFailed("the repair flow names no surface")
        return self.surface

    @property
    def service(self) -> str:
        return self.surface_to_repair.service

    def start(self) -> Continue[...]:
        """Hand the book to its root, which records the pages someone left uncommitted so no turn is sent them and no commit takes them."""
        rooted = RootedBook.model_validate(
            self.handoff(RootBook, parent_records_dir=str(self.records_dir), service=self.service)
        )
        return Continue(rooted, self.plan_first_round, uncommitted_at_start=rooted.uncommitted_at_start).because("the book is rooted")

    def plan_first_round(self, uncommitted_at_start: tuple[str, ...]) -> Continue[...] | Done:
        """Plan the pages the repair works on: each page the check or the failed run finds a problem on, but one someone left uncommitted."""
        run_problems = [problem for problems in self.run_failures.values() for problem in problems]
        problems = (*page_problems(self.root, self.service), *run_problems)
        by_page = problems_by_page(problems, frozenset(uncommitted_at_start))
        journey = journey_pages(self.root, self.service, frozenset(uncommitted_at_start))
        ledger = RepairLedger(uncommitted_at_start=uncommitted_at_start, planned_pages=tuple(by_page), journey=journey)
        return self._pack_round(ledger, RepairRound(number=1), by_page, problems)

    def plan_round(self, ledger: RepairLedger, last: RepairRound, problems: tuple[PageProblem, ...]) -> Continue[...] | Done:
        """Pack the planned pages still open that have problems now. A spent repair ends with what is left."""
        current_problems_by_page = problems_by_page(problems, frozenset(ledger.uncommitted_at_start))
        by_page = {page: on_page for page, on_page in current_problems_by_page.items() if page in ledger.planned_pages and page not in ledger.closed_pages}
        outside = sorted(set(current_problems_by_page) - set(ledger.planned_pages))
        if outside:
            self.logger.info("%d pages outside this repair have problems, left for the book check: %s", len(outside), ", ".join(outside))
        reopened = sorted(set(current_problems_by_page) & set(ledger.closed_pages))
        if reopened:
            self.logger.info("%d pages a batch closed have problems again, left for the book check: %s", len(reopened), ", ".join(reopened))
        if last.number >= REPAIR_ROUNDS:
            return Done(ledger.outcome(last.number, by_page)).because("the repair rounds are spent")
        current_journey = journey_pages(self.root, self.service, frozenset(ledger.uncommitted_at_start))
        unplanned_flow_pages = sorted(set(current_journey.flow_pages) - set(ledger.journey.pages))
        if unplanned_flow_pages:
            self.logger.info(
                "%d flow pages written after the repair planned its journey, left for the book check: %s",
                len(unplanned_flow_pages),
                ", ".join(unplanned_flow_pages),
            )
        return self._pack_round(ledger, RepairRound(number=last.number + 1), by_page, problems)

    def _pack_round(
        self,
        ledger: RepairLedger,
        this_round: RepairRound,
        by_page: dict[str, tuple[PageProblem, ...]],
        problems: tuple[PageProblem, ...],
    ) -> Continue[...] | Done:
        packed = pack_repairs(self.root, by_page, ledger.journey, pages_needing_journey(problems))
        reported = {part.subject for part in ledger.oversized_parts}
        oversized_parts = (*ledger.oversized_parts, *(part for part in packed.oversized_parts if part.subject not in reported))
        ledger = ledger.model_copy(update={"oversized_parts": oversized_parts})
        this_round = this_round.model_copy(update={"batches": packed.batches})
        if not packed.batches:
            return Done(ledger.outcome(this_round.number - 1, by_page)).because("no planned page is left for a turn")
        pages = sum(len(batch.pages) for batch in packed.batches)
        self.logger.info("round %d repairs %d pages in %d turns", this_round.number, pages, len(packed.batches))
        return Continue(
            len(packed.batches),
            self.prepare_batch_turn,
            ledger=ledger,
            this_round=this_round,
            index=0,
            problems_at_turn_start=tuple(problems),
        ).because("prepare the first batch")

    def prepare_batch_turn(
        self, ledger: RepairLedger, this_round: RepairRound, index: int, problems_at_turn_start: tuple[PageProblem, ...]
    ) -> Continue[...]:
        """Snapshot the tree and write the command state that scopes the turn's check to its batch and to the problems the book has now."""
        batch = this_round.batches[index]
        before = snapshot(self.root)
        state = WriterCommandState(
            root=self.root,
            service=self.service,
            pages=batch.page_paths,
            sections_by_page={page.page: page.sections for page in batch.pages if page.sections},
            problems_at_turn_start=problems_at_turn_start,
        )
        _ = write_command_state(self.run_dir, state)
        return Continue(batch.page_paths, self.repair_batch, ledger=ledger, this_round=this_round, index=index, before=before).because(
            "repair the batch"
        )

    def repair_batch(self, ledger: RepairLedger, this_round: RepairRound, index: int, before: Snapshot) -> Continue[...]:
        """One turn, confined to the book folder and to ostler, the scoped check and the scenario run, repairs one batch of pages. A turn that ends without a reply joins the failed ones."""
        batch = this_round.batches[index]
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
            self.logger.warning("%s", failure)
            ledger = ledger.model_copy(update={"failed_turns": (*ledger.failed_turns, failure)})
        node = Path(REPAIR_PROMPT).stem
        metric = turn_metric(Phase.WRITE, node, (self.service,), (time.monotonic() - started) / 60, self.turn_usage(node))
        return Continue(
            failure, self.record_repair_turn, ledger=ledger, this_round=this_round, index=index, before=before, metric=metric
        ).because("record what the turn cost")

    def record_repair_turn(
        self, ledger: RepairLedger, this_round: RepairRound, index: int, before: Snapshot, metric: TurnMetric
    ) -> Continue[...]:
        """Record what the repair turn cost."""
        record_turn(self.records_dir, metric)
        return Continue(metric, self.put_back_outside_book, ledger=ledger, this_round=this_round, index=index, before=before).because(
            "put back what the turn changed outside its book"
        )

    def put_back_outside_book(self, ledger: RepairLedger, this_round: RepairRound, index: int, before: Snapshot) -> Continue[...]:
        """Put back each path the turn changed outside the book."""
        stray = put_back_outside(self.root, self.service, before, self.run_dir)
        for path in stray:
            self.logger.warning("put back %s, which the repair turn changed outside its book", path)
        return Continue(stray, self.put_back_pages_batch_may_not_keep, ledger=ledger, this_round=this_round, index=index, before=before).because(
            "put back the book pages the turn may not keep"
        )

    def put_back_pages_batch_may_not_keep(self, ledger: RepairLedger, this_round: RepairRound, index: int, before: Snapshot) -> Continue[...] | Await[...]:
        """Put back each book page the turn changed but may not keep: the entries page, a page its batch does not own, and a page an earlier batch closed.

        A page someone left uncommitted has no committed copy of their edit to go back to, so a turn
        that changed one waits for the operator.
        """
        changes = turn_changes(self.root, self.service, before, this_round.batches[index], ledger.closed_pages)
        unrestorable_uncommitted = restore(self.root, changes.to_put_back, before)
        for path in sorted(set(changes.to_put_back) - set(unrestorable_uncommitted) - {changes.entries_page}):
            self.logger.warning("put back %s, which the repair turn changed outside the pages its batch owns", path)
        kept = list(changes.kept)
        if unrestorable_uncommitted:
            return Await(
                self.run_dir / UNCOMMITTED_PAGE_GATE,
                "The repair turn changed pages someone left uncommitted, and code has no copy of their edits to put back:\n\n"
                + "\n".join(f"- {path}" for path in unrestorable_uncommitted)
                + "\n\nSort each page out in the repo, then answer here. No commit takes these pages.",
                self.put_back_entry_overreach,
                ledger=ledger,
                this_round=this_round,
                index=index,
                before=before,
                kept=kept,
            ).because("the repair turn changed a page someone left uncommitted")
        return Continue(
            changes.to_put_back, self.put_back_entry_overreach, ledger=ledger, this_round=this_round, index=index, before=before, kept=kept
        ).because("put back the entry pages the turn changed beyond link lines")

    def put_back_entry_overreach(
        self, ledger: RepairLedger, this_round: RepairRound, index: int, before: Snapshot, kept: list[str]
    ) -> Continue[...]:
        """Put back each entry page the turn kept but changed beyond adding link lines."""
        overreach = entry_pages_changed_beyond_links(self.root, this_round.batches[index], kept)
        _ = restore(self.root, overreach, before)
        for path in overreach:
            self.logger.warning("put back %s, an entry page the repair turn changed beyond adding link lines", path)
        return Continue(overreach, self.stamp_pages, ledger=ledger, this_round=this_round, index=index, before=before).because(
            "stamp the repaired pages"
        )

    def stamp_pages(self, ledger: RepairLedger, this_round: RepairRound, index: int, before: Snapshot) -> Continue[...]:
        """Stamp each page the turn changed that its batch owns, but the entries page and the pages someone left uncommitted."""
        batch = this_round.batches[index]
        pages = pages_to_stamp(self.root, self.service, before, batch)
        changed_journey_pages = sorted(set(pages) - set(batch.page_paths))
        if changed_journey_pages:
            self.logger.info("the repair turn also changed %d journey pages: %s", len(changed_journey_pages), ", ".join(changed_journey_pages))
        stamp_repaired_pages(self.root, pages)
        return Continue(pages, self.commit_pages, ledger=ledger, this_round=this_round, index=index, pages=pages).because(
            "commit the repaired pages"
        )

    def commit_pages(self, ledger: RepairLedger, this_round: RepairRound, index: int, pages: tuple[str, ...]) -> Continue[...] | Await[...]:
        """Commit the batch's pages. A refused commit waits for the operator."""
        refusal = commit_returning_refusal(self.root, repaired_book_commit_subject(self.service), *pages)
        if refusal:
            return self._await_operator_on_refused_commit(refusal, self.commit_pages, ledger=ledger, this_round=this_round, index=index, pages=pages)
        return Continue(pages, self.close_batch, ledger=ledger, this_round=this_round, index=index).because(
            "close the pages the batch left clean"
        )

    def close_batch(self, ledger: RepairLedger, this_round: RepairRound, index: int) -> Continue[...]:
        """Check the book, close each page of the batch the check finds clean, and move to the next batch, or plan the next round after the last."""
        problems = page_problems(self.root, self.service)
        ledger = ledger.with_clean_pages_closed(this_round, index, problems)
        if index + 1 < len(this_round.batches):
            return Continue(
                ledger.closed_pages,
                self.prepare_batch_turn,
                ledger=ledger,
                this_round=this_round,
                index=index + 1,
                problems_at_turn_start=tuple(problems),
            ).because("prepare the next batch")
        return Continue(ledger.closed_pages, self.plan_round, ledger=ledger, last=this_round, problems=problems).because(
            "plan the next round"
        )
