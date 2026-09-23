"""Garbage collection after each aggregation job: which pages nothing reaches that the job may delete.

A page of the job's service that nothing reaches is deleted when the job owns it, or when the job created
it: a page HEAD did not track before the job's commit. Every other page nothing reaches is left for the
report. That covers a page already unreachable when the queue froze, a page an earlier job wrote, and a
queued page an earlier job unlinked. The queued page's own job still runs, so the work set never changes
mid-run, and the page is collected after that job if nothing reaches it then.
"""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ostler.book_reach import DeadPage
from workhorse_workflows.okf_book.shared.jobs import Job
from workhorse_workflows.okf_book.shared.page_check import dead_book_pages


def delete_book_pages(root: Path, pages: Iterable[str]) -> None:
    """Delete each repo-relative page. A page already gone is skipped, so the same list can be deleted twice."""
    for page in pages:
        (root / page).unlink(missing_ok=True)


def collectable(root: Path, job: Job, created: Iterable[str]) -> tuple[DeadPage, ...]:
    """The pages of the job's service that nothing reaches and that the job may delete."""
    deletable = job.owned_pages | frozenset(created)
    return tuple(page for page in dead_book_pages(root) if page.service == job.service and page.rel in deletable)
