"""What the repair of a book carries: each round's batches, the ledger it keeps from round to round, and what it leaves."""
from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict

from workhorse_workflows.okf_book.main.nodes.journey import JourneyPages
from workhorse_workflows.okf_book.main.nodes.repair_batches import OversizedPart, RepairBatch
from workhorse_workflows.okf_book.shared.page_check import PageProblem


class RepairOutcome(BaseModel):
    """What the repair left: the rounds it ran, the turns that ended without a reply, the pages and sections too large for one writer, and how many problems remain on the pages it repaired."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rounds: int
    failed_turns: tuple[str, ...] = ()
    oversized_parts: tuple[OversizedPart, ...] = ()
    problem_count_left: int = 0


class RepairRound(BaseModel):
    """One round of the repair: its number and its batches."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    number: int
    batches: tuple[RepairBatch, ...] = ()


class RepairLedger(BaseModel):
    """What the repair carries from round to round: the book pages someone left uncommitted when it started, which no turn may touch, the pages the first round planned and the journey pages it planned, the turns that failed so far, the pages and sections too large for one writer, and the pages a batch closed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    uncommitted_at_start: tuple[str, ...]
    planned_pages: tuple[str, ...]
    journey: JourneyPages
    failed_turns: tuple[str, ...] = ()
    oversized_parts: tuple[OversizedPart, ...] = ()
    closed_pages: tuple[str, ...] = ()

    def with_clean_pages_closed(self, this_round: RepairRound, index: int, problems: Iterable[PageProblem]) -> RepairLedger:
        """This ledger with each page of the round's batch at `index` the check finds no problem on added to its closed pages.

        An entry page stays open while a later batch of the round owns the journey, since that batch
        may add link lines to it. After the last such batch, the clean entry pages of every earlier
        batch close too.
        """
        batches = this_round.batches
        open_pages = {problem.page for problem in problems}
        entry_pages = set(self.journey.entry_pages)
        journey_ahead = any(batch.journey is not None for batch in batches[index + 1 :])
        earlier_entry_pages = () if journey_ahead else (page for batch in batches[:index] for page in batch.page_paths if page in entry_pages)
        closable_batch_pages = (page for page in batches[index].page_paths if not (journey_ahead and page in entry_pages))
        closed = (page for page in dict.fromkeys((*earlier_entry_pages, *closable_batch_pages)) if page not in open_pages and page not in self.closed_pages)
        return self.model_copy(update={"closed_pages": (*self.closed_pages, *closed)})

    def outcome(self, rounds: int, by_page: dict[str, tuple[PageProblem, ...]]) -> RepairOutcome:
        left = sum(len(problems) for problems in by_page.values())
        return RepairOutcome(rounds=rounds, failed_turns=self.failed_turns, oversized_parts=self.oversized_parts, problem_count_left=left)
