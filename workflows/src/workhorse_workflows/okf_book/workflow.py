"""The okf-book workflow: enumerate a service's book and the production files it has to describe."""
from __future__ import annotations

from pathlib import Path

from workhorse.cli import console_script
from workhorse.pyflow import Await, Continue, Done, Registry, Workflow
from workhorse_workflows.kit import commit_paths
from workhorse_workflows.okf_book.budget import ALONE_CEILING_TOKENS
from workhorse_workflows.okf_book.entries import (
    book_dir,
    merged_links,
    read_entries,
    services,
    write_entries,
)
from workhorse_workflows.okf_book.listing import listing_context
from workhorse_workflows.okf_book.production import book_citations, production_files
from workhorse_workflows.okf_book.prune import commit_removal, orphaned_pages, remove_page
from workhorse_workflows.okf_book.stubs import write_stubs
from workhorse_workflows.okf_book.surface import EntryPointListing, Surface
from workhorse_workflows.okf_book.work_set import WorkSet, cited_digests, freeze, unstamped_files

class OkfBook(Workflow):
    """Phase 1: fix the work set a run documents, starting a book from its surfaces on a cold start."""

    surfaces: tuple[Surface, ...] = ()
    merge_pass: bool = False

    @property
    def root(self) -> Path:
        return Path(self.repo_dir).resolve()

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
            "prompts/list-entry-points.md",
            returns=EntryPointListing,
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
        """Find every page whose source is gone, before any is deleted."""
        root = self.root
        orphans = tuple(page for service in services(root) for page in orphaned_pages(root, service))
        if not orphans:
            return Continue(orphans, self.enumerate_files, pruned=orphans)
        return Continue(orphans, self.delete_orphan, orphans=orphans, index=0)

    def delete_orphan(self, orphans: tuple[str, ...], index: int) -> Continue[...]:
        """Delete one orphaned page and its entries links. Its commit is the next state, so a failed commit retries alone."""
        paths = remove_page(self.root, orphans[index])
        return Continue(paths, self.commit_deletion, orphans=orphans, index=index, paths=paths)

    def commit_deletion(self, orphans: tuple[str, ...], index: int, paths: tuple[str, ...]) -> Continue[...]:
        """Commit one deleted page on its own, then move to the next orphan."""
        committed = commit_removal(self.root, orphans[index], paths)
        if index + 1 < len(orphans):
            return Continue(committed, self.delete_orphan, orphans=orphans, index=index + 1)
        return Continue(committed, self.enumerate_files, pruned=orphans)

    def enumerate_files(self, pruned: tuple[str, ...]) -> Done:
        """Walk every service's entry points, keep what a merge changed on a merge pass, and freeze the result."""
        root = self.root
        names = services(root)
        files = frozenset(path for service in names for path in production_files(root, service))
        if self.merge_pass:
            files = unstamped_files(root, files, cited_digests(book_citations(root, names)))
        work_set = WorkSet(services=names, files=tuple(sorted(files)), pruned=pruned)
        return Done(freeze(self.run_dir, work_set))


workflow = (
    Registry("okf-book", package=__package__)
    .add_blueprints()
    .stub_agents({"list-entry-points": {"entry_points": [{"slug": "home", "title": "Home"}]}})
)

main = console_script(workflow.entry_point(OkfBook))
