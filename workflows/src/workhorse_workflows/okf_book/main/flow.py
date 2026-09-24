"""The okf-book run: fix the work list, hand it to the document, aggregate and exercise flows, then publish the report."""
from __future__ import annotations

from typing import cast

from workhorse.pyflow import Await, Continue, Done, Transition
from workhorse.worklist import WorkItem
from workhorse_workflows.kit import commit_paths
from workhorse_workflows.okf_book.aggregate import Aggregate
from workhorse_workflows.okf_book.document import Document
from workhorse_workflows.okf_book.exercise import Exercise
from workhorse_workflows.okf_book.main.nodes.listing import listing_context
from workhorse_workflows.okf_book.main.nodes.prune import commit_removal, orphaned_pages, remove_page
from workhorse_workflows.okf_book.main.nodes.report import build_report, read_report, write_report
from workhorse_workflows.okf_book.main.nodes.stub_pages import write_stubs
from workhorse_workflows.okf_book.main.nodes.surface import EntryPointListing, Surface
from workhorse_workflows.okf_book.main.nodes.unstamped import cited_digests, unstamped_files
from workhorse_workflows.okf_book.shared.blockers import read_blockers
from workhorse_workflows.okf_book.shared.book_flow import BookFlow
from workhorse_workflows.okf_book.shared.budget import ALONE_CEILING_TOKENS
from workhorse_workflows.okf_book.shared.entries import (
    book_dir,
    merged_links,
    read_entries,
    services,
    write_entries,
)
from workhorse_workflows.okf_book.shared.production import book_citations, production_files
from workhorse_workflows.okf_book.shared.work import DONE, FILE, ORPHAN, seed

OPERATOR_NAME = "operator.md"


class OkfBook(BookFlow):
    """The run: stub a cold start's surfaces, prune the orphans, fix the files, then document, aggregate and exercise them."""

    surfaces: tuple[Surface, ...] = ()
    merge_pass: bool = False

    def start(self) -> Continue[...]:
        """A cold start lists each declared surface first. Otherwise the book already has its roots."""
        if self.surfaces:
            return Continue(None, self.list_entry_points, index=0)
        return Continue(None, self.prune_pages)

    def list_entry_points(self, index: int) -> Continue[...] | Await[...]:
        """One turn reads the surface's entry file and its nearest imports, and names its entry points."""
        surface = self.surfaces[index]
        context = listing_context(self.root, surface)
        if not context.entry_fits():
            return Await(
                self.run_dir / f"{surface.service}-entry.md",
                f"{surface.entry} is gone, or past the {ALONE_CEILING_TOKENS} tokens one turn can read. "
                + "Restore or split it, then answer here to list its entry points again.",
                self.list_entry_points,
                index=index,
            )
        listing = self.agent(
            "main/prompts/list-entry-points.md",
            returns=EntryPointListing,
            power="medium",
            args=context.template_args(),
        )
        return Continue(listing, self.stub_surface, index=index, listing=listing)

    def stub_surface(self, index: int, listing: EntryPointListing) -> Continue[...]:
        """Scaffold a page per entry point and link each from entries.md. A retry keeps what exists."""
        surface = self.surfaces[index]
        root = self.root
        links = write_stubs(root, surface, listing.entry_points)
        entries = write_entries(root, surface.service, merged_links(read_entries(root, surface.service), links))
        pages = {book_dir(root, surface.service) / link.target.partition("#")[0] for link in links}
        paths = tuple(sorted(path.relative_to(root).as_posix() for path in {*pages, entries}))
        return Continue(links, self.commit_stubs, index=index, paths=paths)

    def commit_stubs(self, index: int, paths: tuple[str, ...]) -> Continue[...]:
        """Commit the stub pages and the entries page. A retry after the commit landed finds nothing to commit."""
        surface = self.surfaces[index]
        message = f"docs({surface.service}): stub the {surface.kind.value} entry points"
        committed = commit_paths(self.root, message, *paths)
        if index + 1 < len(self.surfaces):
            return Continue(committed, self.list_entry_points, index=index + 1)
        return Continue(committed, self.prune_pages)

    def prune_pages(self) -> Continue[...]:
        """Seed every page whose source is gone, before any is deleted."""
        root = self.root
        orphans = (page for service in services(root) for page in orphaned_pages(root, service))
        seed(self.work, ORPHAN, (WorkItem(id=page, kind=ORPHAN, order=order) for order, page in enumerate(orphans)))
        return Continue(None, self.delete_orphans)

    def delete_orphans(self) -> Transition:
        """Take the next orphaned page off the list. A drained list moves on to the files."""
        items = self.work.claim(1, kind=ORPHAN)
        if not items:
            return Continue(None, self.enumerate_files)
        return self._delete_orphan(items)

    def _delete_orphan(self, items: list[WorkItem]) -> Continue[...]:
        """Delete one orphaned page and its entries links. Its commit is the next state, so a failed commit retries alone."""
        page = items[0].id
        return Continue(page, self.commit_deletion, page=page, paths=remove_page(self.root, page))

    def commit_deletion(self, page: str, paths: tuple[str, ...]) -> Continue[...]:
        """Commit one deleted page on its own and settle its row, then take the next orphan."""
        committed = commit_removal(self.root, page, paths)
        _ = self.work.settle([page], DONE, ORPHAN)
        return Continue(committed, self.delete_orphans)

    def enumerate_files(self) -> Continue[...]:
        """Walk every service's entry points, keep what a merge changed on a merge pass, and seed the files."""
        root = self.root
        names = services(root)
        files = frozenset(path for service in names for path in production_files(root, service))
        if self.merge_pass:
            files = unstamped_files(root, files, cited_digests(book_citations(root, names)))
        seed(self.work, FILE, (WorkItem(id=file, kind=FILE, order=order) for order, file in enumerate(sorted(files))))
        return Continue(len(files), self.document, services=names)

    def document(self, services: tuple[str, ...]) -> Continue[...]:
        """Every file on the list gets a contract."""
        documented = cast(object, self.handoff(Document, parent_records_dir=str(self.records_dir)))
        return Continue(documented, self.aggregate, services=services)

    def aggregate(self, services: tuple[str, ...]) -> Continue[...]:
        """The contracts are aggregated into the book, one job at a time."""
        aggregated = cast(object, self.handoff(Aggregate, parent_records_dir=str(self.records_dir), services=services))
        return Continue(aggregated, self.exercise, services=services)

    def exercise(self, services: tuple[str, ...]) -> Continue[...]:
        """The book brings the stack up, and its flows run."""
        exercised = cast(object, self.handoff(Exercise, parent_records_dir=str(self.records_dir), services=services))
        return Continue(exercised, self.report, services=services)

    def report(self, services: tuple[str, ...]) -> Await[...] | Done:
        """Publish the report. Any blocker from any phase stops the run at the operator, once."""
        report = build_report(self.root, self.records_dir, self.work, services)
        page = write_report(self.records_dir, report)
        blockers = read_blockers(self.records_dir)
        if not blockers:
            return Done(report)
        return Await(
            self.run_dir / OPERATOR_NAME,
            f"The run stopped on {len(blockers)} blockers, each listed in {page}. "
            + "Fix the book, ostler, the app or the workflow each one names, then restart the run. "
            + "Answer here to close this run.",
            self.finish,
        )

    def finish(self) -> Done:
        """The operator has read the report."""
        return Done(read_report(self.records_dir))
