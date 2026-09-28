"""What code does with one repair turn's changes: put back what its batch may not keep, then stamp and commit the rest.

Code puts back each page a turn changed that its batch may not keep, by the rules of `nodes/repair_put_back.py`.

A page someone left uncommitted when the repair started has no committed copy of their edit to go
back to, so a turn that changed one waits for the operator. A commit the repo refuses waits for them too.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from workhorse.pyflow import Await, Continue, Done
from workhorse_workflows.okf_book.main.nodes.repair_batch_models import RepairBatch
from workhorse_workflows.okf_book.main.nodes.repair_put_back import (
    entry_pages_changed_beyond_links,
    pages_to_stamp,
    stamp_repaired_pages,
    turn_changes,
)
from workhorse_workflows.okf_book.shared.book_commits import repaired_book_commit_subject
from workhorse_workflows.okf_book.shared.book_flow import BookFlow
from workhorse_workflows.okf_book.shared.confine import Snapshot, put_back_outside, restore

UNCOMMITTED_PAGE_GATE = "uncommitted-page-changed.md"


class SettledTurn(BaseModel):
    """What the repair reads back from a settled turn: the pages it committed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pages: tuple[str, ...] = ()


class SettleRepairTurn(BookFlow):
    """Puts back what one repair turn changed but its batch may not keep, then stamps and commits the pages it repaired."""

    service: str = ""
    batch: RepairBatch
    closed_pages: tuple[str, ...] = ()
    before: Snapshot
    repair_run_dir: str = ""

    def start(self) -> Continue[...]:
        """Put back each path the turn changed outside the book, but the repair's own run directory."""
        stray = put_back_outside(self.root, self.service, self.before, Path(self.repair_run_dir))
        for path in stray:
            self.logger.warning("put back %s, which the repair turn changed outside its book", path)
        return Continue(stray, self.put_back_pages_batch_may_not_keep).because("put back the book pages the turn may not keep")

    def put_back_pages_batch_may_not_keep(self) -> Continue[...] | Await[...]:
        """Put back each book page the turn changed but may not keep: the entries page, a page its batch does not own, and a page an earlier batch closed.

        A page someone left uncommitted has no committed copy of their edit to go back to, so a turn
        that changed one waits for the operator.
        """
        changes = turn_changes(self.root, self.service, self.before, self.batch, self.closed_pages)
        unrestorable_uncommitted = restore(self.root, changes.to_put_back, self.before)
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
                kept=kept,
            ).because("the repair turn changed a page someone left uncommitted")
        return Continue(changes.to_put_back, self.put_back_entry_overreach, kept=kept).because(
            "put back the entry pages the turn changed beyond link lines"
        )

    def put_back_entry_overreach(self, kept: list[str]) -> Continue[...]:
        """Put back each entry page the turn kept but changed beyond adding link lines."""
        overreach = entry_pages_changed_beyond_links(self.root, self.batch, kept)
        _ = restore(self.root, overreach, self.before)
        for path in overreach:
            self.logger.warning("put back %s, an entry page the repair turn changed beyond adding link lines", path)
        return Continue(overreach, self.stamp_pages).because("stamp the repaired pages")

    def stamp_pages(self) -> Continue[...]:
        """Stamp each page the turn changed that its batch owns, but the entries page and the pages someone left uncommitted."""
        pages = pages_to_stamp(self.root, self.service, self.before, self.batch)
        changed_journey_pages = sorted(set(pages) - set(self.batch.page_paths))
        if changed_journey_pages:
            self.logger.info("the repair turn also changed %d journey pages: %s", len(changed_journey_pages), ", ".join(changed_journey_pages))
        stamp_repaired_pages(self.root, pages)
        return Continue(pages, self.commit_pages, pages=pages).because("commit the repaired pages")

    def commit_pages(self, pages: tuple[str, ...]) -> Await[...] | Done:
        """Commit the batch's pages. A refused commit waits for the operator."""
        refusal = self._commit(repaired_book_commit_subject(self.service), *pages)
        if refusal:
            return self._await_operator_on_refused_commit(refusal, self.commit_pages, pages=pages)
        return Done(SettledTurn(pages=pages)).because("the repaired pages are committed")
