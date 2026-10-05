"""The repair of a book: once its root is committed, one confined turn per batch of problem pages fixes them, round after round.

A book goes to its repair when it is too large for one writer. When the book failed its run, the
run's failures are the first round's problems on the pages they cover.

The first round fixes the pages the repair works on. A later round repairs what is left on those
pages, and a problem found on any other page is left for the book check to report. A page the check
found clean after its batch is closed: code puts it back when a later turn changes it, and a problem
it has later is left for the book check, so no turn repairs it twice. An entry page closes only
after the round's last batch that may add link lines to it. A page too large for one writer is sent to no turn and
reported.

After each turn the repair hands its changes to `settle_repair_turn_flow.py`, which puts back what
the batch may not keep and commits the rest.

A problem the last lead of the book's page check held for another side than the book is sent to no
turn, and each page a group the lead named the book's sits on is told first what the lead said of it.

A page someone left uncommitted when the repair started is never sent to a turn and never committed,
so their edits stay theirs. A turn that changed one waits for the operator.
"""
from __future__ import annotations

import time
from pathlib import Path

from workhorse.pyflow import AgentTimeout, AgentTurnFailed, Continue, Done, WorkflowFailed
from workhorse_workflows.okf_book.main.nodes.check_lead import latest_check_findings, unheld, with_check_instructions
from workhorse_workflows.okf_book.main.nodes.journey import journey_pages
from workhorse_workflows.okf_book.main.nodes.lead_findings import read_findings
from workhorse_workflows.okf_book.main.nodes.operator_answer import read_answer
from workhorse_workflows.okf_book.main.nodes.repair_batches import has_work_left, pack_repairs, problems_by_page
from workhorse_workflows.okf_book.main.nodes.repair_ledger import BatchTurn, RepairLedger, RepairRound
from workhorse_workflows.okf_book.main.nodes.surface import Surface
from workhorse_workflows.okf_book.main.nodes.writer_commands import WriterCommandState, write_command_state
from workhorse_workflows.okf_book.main.nodes.writer_jobs import settle_jobs
from workhorse_workflows.okf_book.main.nodes.writer_request import writer_request
from workhorse_workflows.okf_book.main.root_book_flow import RootBook, RootedBook
from workhorse_workflows.okf_book.main.settle_repair_turn_flow import SettledTurn, SettleRepairTurn
from workhorse_workflows.okf_book.shared.blockers import Phase
from workhorse_workflows.okf_book.shared.book_flow import BookFlow
from workhorse_workflows.okf_book.shared.confine import snapshot
from workhorse_workflows.okf_book.shared.metrics import TurnMetric, record_turn, turn_metric
from workhorse_workflows.okf_book.shared.page_check import PageProblem, page_problems

REPAIR_PROMPT = "main/prompts/repair-pages.md"
REPAIR_ROUNDS = 3


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

    def _book_problems(self) -> tuple[PageProblem, ...]:
        findings = latest_check_findings(read_findings(self.records_dir), self.service)
        return with_check_instructions(unheld(page_problems(self.root, self.service), findings), findings)

    def plan_first_round(self, uncommitted_at_start: tuple[str, ...]) -> Continue[...] | Done:
        """Plan the pages the repair works on: each page the check or the failed run finds a problem on, but one someone left uncommitted."""
        run_problems = [problem for problems in self.run_failures.values() for problem in problems]
        problems = (*self._book_problems(), *run_problems)
        by_page = problems_by_page(problems, frozenset(uncommitted_at_start))
        journey = journey_pages(self.root, self.service, frozenset(uncommitted_at_start))
        ledger = RepairLedger(uncommitted_at_start=uncommitted_at_start, planned_pages=tuple(by_page), journey=journey)
        return self._pack_round(ledger, RepairRound(number=1), by_page, problems)

    def plan_round(self, ledger: RepairLedger, finished_round: RepairRound, problems: tuple[PageProblem, ...]) -> Continue[...] | Done:
        """Pack the planned pages still open that have problems now. A spent repair ends with what is left."""
        current_problems_by_page = problems_by_page(problems, frozenset(ledger.uncommitted_at_start))
        by_page = {page: on_page for page, on_page in current_problems_by_page.items() if page in ledger.planned_pages and page not in ledger.closed_pages}
        outside = sorted(set(current_problems_by_page) - set(ledger.planned_pages))
        if outside:
            self.logger.info("%d pages outside this repair have problems, left for the book check: %s", len(outside), ", ".join(outside))
        reopened = sorted(set(current_problems_by_page) & set(ledger.closed_pages))
        if reopened:
            self.logger.info("%d pages a batch closed have problems again, left for the book check: %s", len(reopened), ", ".join(reopened))
        if finished_round.number >= REPAIR_ROUNDS:
            return Done(ledger.outcome(finished_round.number, by_page)).because("the repair rounds are spent")
        current_journey = journey_pages(self.root, self.service, frozenset(ledger.uncommitted_at_start))
        unplanned_flow_pages = sorted(set(current_journey.flow_pages) - set(ledger.journey.pages))
        if unplanned_flow_pages:
            self.logger.info(
                "%d flow pages written after the repair planned its journey, left for the book check: %s",
                len(unplanned_flow_pages),
                ", ".join(unplanned_flow_pages),
            )
        return self._pack_round(ledger, RepairRound(number=finished_round.number + 1), by_page, problems)

    def _pack_round(
        self,
        ledger: RepairLedger,
        this_round: RepairRound,
        by_page: dict[str, tuple[PageProblem, ...]],
        problems: tuple[PageProblem, ...],
    ) -> Continue[...] | Done:
        packed = pack_repairs(self.root, by_page, ledger.journey)
        reported = {part.subject for part in ledger.oversized_parts}
        oversized_parts = (*ledger.oversized_parts, *(part for part in packed.oversized_parts if part.subject not in reported))
        ledger = ledger.model_copy(update={"oversized_parts": oversized_parts})
        this_round = this_round.model_copy(update={"batches": packed.batches})
        if not packed.batches:
            return Done(ledger.outcome(this_round.number - 1, by_page)).because("no planned page is left for a turn")
        page_count = sum(len(batch.pages) for batch in packed.batches)
        self.logger.info("round %d repairs %d pages in %d turns", this_round.number, page_count, len(packed.batches))
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
        open_pages = frozenset({problem.page for problem in problems_at_turn_start} | (set(self.run_failures) if this_round.number == 1 else set()))
        if not has_work_left(self.root, this_round.batches[index], open_pages):
            self.logger.info("no turn for %s: earlier turns of the round left nothing to repair there", ", ".join(this_round.batches[index].page_paths))
            return Continue(index, self.close_batch, ledger=ledger, this_round=this_round, index=index).because(
                "earlier turns left this batch nothing to repair"
            )
        turn = BatchTurn(ledger=ledger, this_round=this_round, index=index, before=snapshot(self.root))
        batch = turn.batch
        state = WriterCommandState(
            root=self.root,
            service=self.service,
            pages=batch.page_paths,
            sections_by_page={page.page: page.sections for page in batch.pages if page.sections},
            problems_at_turn_start=problems_at_turn_start,
            records_dir=self.records_dir,
        )
        settle_jobs(self.run_dir)
        _ = write_command_state(self.run_dir, state)
        return Continue(batch.page_paths, self.repair_batch, turn=turn).because("repair the batch")

    def repair_batch(self, turn: BatchTurn) -> Continue[...]:
        """One turn, confined to the book folder and to ostler, the scoped check and the scenario run, repairs one batch of pages. A turn that ends without a reply joins the failed ones."""
        batch = turn.batch
        request = writer_request(self.run_dir, self.root, self.surface_to_repair, self.book_folder, self.source_folder)
        started = time.monotonic()
        failure = ""
        try:
            _ = self.agent(
                REPAIR_PROMPT,
                returns=str,
                power="medium",
                timeout=float("inf"),
                args=request.repair_template_args(batch, failed_run=bool(self.run_failures), operator_answer=read_answer(self.records_dir)),
                cwd=self.root / self.book_folder,
                add_dirs=[request.source_view],
                profile=request.repair_profile,
            )
        except (AgentTurnFailed, AgentTimeout) as ended:
            failure = f"the repair turn on {', '.join(batch.page_paths)} ended without a reply: {ended}"
            self.logger.warning("%s", failure)
            ledger = turn.ledger.model_copy(update={"failed_turns": (*turn.ledger.failed_turns, failure)})
            turn = turn.model_copy(update={"ledger": ledger})
        settle_jobs(self.run_dir)
        node = Path(REPAIR_PROMPT).stem
        metric = turn_metric(Phase.WRITE, node, (self.service,), (time.monotonic() - started) / 60, self.turn_usage(node))
        return Continue(failure, self.record_repair_turn, turn=turn, metric=metric).because("record what the turn cost")

    def record_repair_turn(self, turn: BatchTurn, metric: TurnMetric) -> Continue[...]:
        """Record what the repair turn cost."""
        record_turn(self.records_dir, metric)
        return Continue(metric, self.settle_turn, turn=turn).because("settle what the turn changed")

    def settle_turn(self, turn: BatchTurn) -> Continue[...]:
        """Hand the turn's changes to be put back where its batch may not keep them, and the rest stamped and committed."""
        settled = SettledTurn.model_validate(
            self.handoff(
                SettleRepairTurn,
                parent_records_dir=str(self.records_dir),
                service=self.service,
                batch=turn.batch,
                closed_pages=turn.ledger.closed_pages,
                before=turn.before,
                repair_run_dir=str(self.run_dir),
            )
        )
        return Continue(
            settled.pages, self.close_batch, ledger=turn.ledger, this_round=turn.this_round, index=turn.index
        ).because("close the pages the batch left clean")

    def close_batch(self, ledger: RepairLedger, this_round: RepairRound, index: int) -> Continue[...]:
        """Check the book, close each page of the batch the check finds clean, and move to the next batch, or plan the next round after the last."""
        problems = self._book_problems()
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
        return Continue(ledger.closed_pages, self.plan_round, ledger=ledger, finished_round=this_round, problems=problems).because(
            "plan the next round"
        )
