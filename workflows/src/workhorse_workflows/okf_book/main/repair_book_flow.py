"""The repair of a book: code roots it, then one confined turn per batch of problem pages fixes them, round after round.

A book goes to its repair when it is too large for one writer. When the book failed its run, the
run's failures are the first round's problems on the pages they cover.

The first round fixes the pages the repair works on. A later round repairs what is left on those
pages, and a problem found on any other page is left for the book check to report. A page too large
for one writer is sent to no turn and reported.

Each batch owns the pages it is sent. A batch with a page no other page reaches, or with an endpoint
on no flow, also owns the journey pages the repair planned: the pages the entries page links, the flow pages, and
a new page in the flow folder, since the fix for either goes there. Code puts back every other page
the turn changed, and the entries page, which only code writes.

A page someone left uncommitted when the repair started is never sent to a turn and never committed,
so their edits stay theirs. A turn that changed one waits for the operator.
"""
from __future__ import annotations

import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from ostler.stamp import stamp_page
from workhorse.pyflow import AgentTimeout, AgentTurnFailed, Await, Continue, Done, WorkflowFailed
from workhorse_workflows.kit import commit_returning_refusal
from workhorse_workflows.okf_book.main.nodes.journey import JourneyPages, journey_pages, pages_needing_journey
from workhorse_workflows.okf_book.main.nodes.repair_batches import RepairBatch, TooLarge, problems_by_page, repair_batches
from workhorse_workflows.okf_book.main.nodes.root_entries import write_root_entries
from workhorse_workflows.okf_book.main.nodes.surface import Surface
from workhorse_workflows.okf_book.main.nodes.writer_commands import WriterCommandState, write_command_state
from workhorse_workflows.okf_book.main.nodes.writer_request import writer_request
from workhorse_workflows.okf_book.shared.blockers import Phase
from workhorse_workflows.okf_book.shared.book_commits import repaired_book_commit_subject, rooted_book_commit_subject
from workhorse_workflows.okf_book.shared.book_flow import BookFlow
from workhorse_workflows.okf_book.shared.confine import Snapshot, book_changes, in_book, put_back_outside, restore, snapshot, untracked
from workhorse_workflows.okf_book.shared.entries import FEATURES_DIR, entries_path
from workhorse_workflows.okf_book.shared.metrics import TurnMetric, record_turn, turn_metric
from workhorse_workflows.okf_book.shared.page_check import PageProblem, page_problems

REPAIR_PROMPT = "main/prompts/repair-pages.md"
REPAIR_ROUNDS = 3
UNCOMMITTED_PAGE_GATE = "uncommitted-page-changed.md"


class RepairOutcome(BaseModel):
    """What the repair left: the rounds it ran, the turns that ended without a reply, the pages too large for one writer, and how many problems remain on the pages it repaired."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rounds: int
    failed_turns: tuple[str, ...] = ()
    too_large: tuple[TooLarge, ...] = ()
    problems_left: int = 0


class RepairRound(BaseModel):
    """One round of the repair: the book pages someone left uncommitted when it started, which no turn may touch, the pages the first round planned and the journey pages it planned, its number, the turns that failed so far, the pages too large for one writer, and its batches."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    uncommitted_at_start: tuple[str, ...]
    planned_pages: tuple[str, ...]
    journey: JourneyPages
    number: int
    failed_turns: tuple[str, ...] = ()
    too_large: tuple[TooLarge, ...] = ()
    batches: tuple[RepairBatch, ...] = ()

    def outcome(self, rounds: int, by_page: dict[str, tuple[str, ...]]) -> RepairOutcome:
        left = sum(len(problems) for problems in by_page.values())
        return RepairOutcome(rounds=rounds, failed_turns=self.failed_turns, too_large=self.too_large, problems_left=left)


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
        uncommitted_at_start = tuple(sorted(path for path in snapshot(self.root).digests if in_book(self.service, path)))
        return Continue(uncommitted_at_start, self.root_book, uncommitted_at_start=uncommitted_at_start).because("root the book")

    def root_book(self, uncommitted_at_start: tuple[str, ...]) -> Continue[...]:
        """Write and commit the entries page of a book that has none, so every check can tell what it reaches."""
        if entries_path(self.root, self.service).is_file():
            return Continue(None, self.plan_first_round, uncommitted_at_start=uncommitted_at_start).because("the book has its root")
        page = write_root_entries(self.root, self.service)
        return Continue(page, self.commit_root, uncommitted_at_start=uncommitted_at_start, page=page).because("commit the entries page")

    def commit_root(self, uncommitted_at_start: tuple[str, ...], page: str) -> Continue[...] | Await[...]:
        """Commit the entries page. A refused commit waits for the operator."""
        refusal = commit_returning_refusal(self.root, rooted_book_commit_subject(self.service), page)
        if refusal:
            return self._commit_refused(refusal, self.commit_root, uncommitted_at_start=uncommitted_at_start, page=page)
        return Continue(page, self.plan_first_round, uncommitted_at_start=uncommitted_at_start).because("the book is rooted")

    def plan_first_round(self, uncommitted_at_start: tuple[str, ...]) -> Continue[...] | Done:
        """Plan the pages the repair works on: each page the check or the failed run finds a problem on, but one someone left uncommitted."""
        run_problems = [PageProblem(page, text) for page, texts in self.run_failures.items() for text in texts]
        problems = (*page_problems(self.root, self.service), *run_problems)
        by_page = problems_by_page(problems, frozenset(uncommitted_at_start))
        journey = journey_pages(self.root, self.service, frozenset(uncommitted_at_start))
        this_round = RepairRound(uncommitted_at_start=uncommitted_at_start, planned_pages=tuple(by_page), journey=journey, number=1)
        return self._first_batch_or_done(this_round, by_page, pages_needing_journey(problems))

    def plan_round(self, last: RepairRound) -> Continue[...] | Done:
        """Check the book again and pack the planned pages that still have problems. A spent repair ends with what is left."""
        problems = page_problems(self.root, self.service)
        found = problems_by_page(problems, frozenset(last.uncommitted_at_start))
        by_page = {page: texts for page, texts in found.items() if page in last.planned_pages}
        outside = sorted(set(found) - set(by_page))
        if outside:
            self.logger.info("%d pages outside this repair have problems, left for the book check: %s", len(outside), ", ".join(outside))
        if last.number >= REPAIR_ROUNDS:
            return Done(last.outcome(last.number, by_page)).because("the repair rounds are spent")
        listed = journey_pages(self.root, self.service, frozenset(last.uncommitted_at_start))
        later = sorted(set(listed.flow_pages) - set(last.journey.pages))
        if later:
            self.logger.info("%d flow pages written after the repair planned its journey, left for the book check: %s", len(later), ", ".join(later))
        this_round = last.model_copy(update={"number": last.number + 1, "batches": ()})
        return self._first_batch_or_done(this_round, by_page, pages_needing_journey(problems))

    def _first_batch_or_done(
        self, this_round: RepairRound, by_page: dict[str, tuple[str, ...]], needs_journey: frozenset[str]
    ) -> Continue[...] | Done:
        packed = repair_batches(self.root, by_page, this_round.journey, needs_journey)
        reported = {page.subject for page in this_round.too_large}
        too_large = (*this_round.too_large, *(page for page in packed.too_large if page.subject not in reported))
        this_round = this_round.model_copy(update={"too_large": too_large, "batches": packed.batches})
        if not packed.batches:
            return Done(this_round.outcome(this_round.number - 1, by_page)).because("no planned page is left for a turn")
        pages = sum(len(batch.pages) for batch in packed.batches)
        self.logger.info("round %d repairs %d pages in %d turns", this_round.number, pages, len(packed.batches))
        return Continue(len(packed.batches), self.prepare_batch_turn, this_round=this_round, index=0).because("prepare the first batch")

    def prepare_batch_turn(self, this_round: RepairRound, index: int) -> Continue[...]:
        """Snapshot the tree, and write the command state that scopes the turn's check to its batch and to the problems the book has now."""
        batch = this_round.batches[index]
        before = snapshot(self.root)
        problems_at_turn_start = tuple(problem.text for problem in page_problems(self.root, self.service))
        state = WriterCommandState(
            root=self.root,
            service=self.service,
            pages=batch.page_paths,
            sections_by_page={page.page: page.sections for page in batch.pages if page.sections},
            problems_at_turn_start=problems_at_turn_start,
        )
        _ = write_command_state(self.run_dir, state)
        return Continue(batch.page_paths, self.repair_batch, this_round=this_round, index=index, before=before).because("repair the batch")

    def repair_batch(self, this_round: RepairRound, index: int, before: Snapshot) -> Continue[...]:
        """One turn, confined to the book folder and to ostler, the scoped check and the scenario run, repairs one batch of pages."""
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
        node = Path(REPAIR_PROMPT).stem
        metric = turn_metric(Phase.WRITE, node, (self.service,), (time.monotonic() - started) / 60, self.turn_usage(node))
        return Continue(
            failure, self.record_repair_turn, this_round=this_round, index=index, before=before, metric=metric, failure=failure
        ).because("record what the turn cost")

    def record_repair_turn(self, this_round: RepairRound, index: int, before: Snapshot, metric: TurnMetric, failure: str) -> Continue[...]:
        """Record what the repair turn cost, and the turn among the failed ones when it ended without a reply."""
        record_turn(self.records_dir, metric)
        if failure:
            self.logger.warning("%s", failure)
            this_round = this_round.model_copy(update={"failed_turns": (*this_round.failed_turns, failure)})
        return Continue(failure, self.put_back, this_round=this_round, index=index, before=before).because("put back what the turn may not keep")

    def put_back(self, this_round: RepairRound, index: int, before: Snapshot) -> Continue[...] | Await[...]:
        """Put back each path the turn changed but may not keep: one outside the book, the entries page, and a page its batch does not own.

        A page someone left uncommitted has no committed copy of their edit to go back to, so a turn
        that changed one waits for the operator.
        """
        root = self.root
        stray = put_back_outside(root, self.service, before, self.run_dir)
        for path in stray:
            self.logger.warning("put back %s, which the repair turn changed outside its book", path)
        batch = this_round.batches[index]
        entries = entries_path(root, self.service).relative_to(root).as_posix()
        changed = book_changes(root, self.service, before)
        created = untracked(root, changed)
        unowned = [path for path in changed if path == entries or path in before.digests or not batch.owns(path, created)]
        unrestorable_uncommitted = restore(root, unowned, before)
        for path in sorted(set(unowned) - set(unrestorable_uncommitted) - {entries}):
            self.logger.warning("put back %s, which the repair turn changed outside the pages its batch owns", path)
        if unrestorable_uncommitted:
            return Await(
                self.run_dir / UNCOMMITTED_PAGE_GATE,
                "The repair turn changed pages someone left uncommitted, and code has no copy of their edits to put back:\n\n"
                + "\n".join(f"- {path}" for path in unrestorable_uncommitted)
                + "\n\nSort each page out in the repo, then answer here. No commit takes these pages.",
                self.stamp_pages,
                this_round=this_round,
                index=index,
                before=before,
            ).because("the repair turn changed a page someone left uncommitted")
        return Continue(stray, self.stamp_pages, this_round=this_round, index=index, before=before).because("stamp the repaired pages")

    def stamp_pages(self, this_round: RepairRound, index: int, before: Snapshot) -> Continue[...]:
        """Stamp each page the turn changed that its batch owns, but the entries page and the pages someone left uncommitted."""
        root = self.root
        batch = this_round.batches[index]
        entries = entries_path(root, self.service).relative_to(root).as_posix()
        changed = book_changes(root, self.service, before)
        created = untracked(root, changed)
        pages = tuple(path for path in changed if path != entries and path not in before.digests and batch.owns(path, created))
        journey = sorted(set(pages) - set(batch.page_paths))
        if journey:
            self.logger.info("the repair turn also changed %d journey pages: %s", len(journey), ", ".join(journey))
        for page in pages:
            if page.endswith(".md") and (root / page).is_file():
                _ = stamp_page(root, root / FEATURES_DIR, page)
        return Continue(pages, self.commit_pages, this_round=this_round, index=index, pages=pages).because("commit the repaired pages")

    def commit_pages(self, this_round: RepairRound, index: int, pages: tuple[str, ...]) -> Continue[...] | Await[...]:
        """Commit the batch's pages and move to the next batch. A refused commit waits for the operator."""
        refusal = commit_returning_refusal(self.root, repaired_book_commit_subject(self.service), *pages)
        if refusal:
            return self._commit_refused(refusal, self.commit_pages, this_round=this_round, index=index, pages=pages)
        if index + 1 < len(this_round.batches):
            return Continue(pages, self.prepare_batch_turn, this_round=this_round, index=index + 1).because("prepare the next batch")
        return Continue(pages, self.plan_round, last=this_round).because("check the book again")
