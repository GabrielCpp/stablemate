"""Which book pages a repair turn changed that its batch may keep, and the stamp on those it keeps.

Each batch owns the pages it is sent, and the pages whose requests failed on what a fixture page it is
sent arranges, since the fix may be the request. A batch with a page no other page reaches, or with an endpoint
on no flow, also owns the journey pages the repair planned: the pages the entries page links, the flow
pages, and a new page in the flow folder, since the fix for either goes there. On a page the entries
page links it may only add link lines. Every batch also owns the book's fixture folder, since a claim's
arrangement is fixed by declaring the fixture it names there, and the batches run one after another.
Every other page the turn changed goes back: the entries page, which only code writes, a page someone
left uncommitted, and a page an earlier batch closed.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ostler.stamp import stamp_page
from workhorse_workflows.okf_book.main.nodes.journey import adds_only_links
from workhorse_workflows.okf_book.main.nodes.repair_batch_models import RepairBatch
from workhorse_workflows.okf_book.shared.confine import Snapshot, book_changes, committed_text
from workhorse_workflows.okf_book.shared.entries import FEATURES_DIR, entries_path

FIXTURES_NAME = "fixtures"


@dataclass(frozen=True, slots=True)
class TurnChanges:
    """The book pages a repair turn changed: those its batch may keep, and those code puts back."""

    entries_page: str
    kept: tuple[str, ...]
    to_put_back: tuple[str, ...]


def turn_changes(root: Path, service: str, before: Snapshot, batch: RepairBatch, closed_pages: tuple[str, ...]) -> TurnChanges:
    """Split the book pages the turn changed into those the batch may keep and those code puts back."""
    entries_page = entries_path(root, service).relative_to(root).as_posix()
    changed = book_changes(root, service, before)
    to_put_back = tuple(
        path
        for path in changed
        if path == entries_page or path in before.digests or path in closed_pages or not _may_keep(service, batch, path)
    )
    return TurnChanges(entries_page, tuple(path for path in changed if path not in to_put_back), to_put_back)


def fixture_folder(service: str) -> str:
    """The repo-relative folder of the service's book that holds its fixture pages."""
    return (FEATURES_DIR / service / FIXTURES_NAME).as_posix()


def _may_keep(service: str, batch: RepairBatch, path: str) -> bool:
    return batch.owns(path) or path.startswith(f"{fixture_folder(service)}/")


def entry_pages_changed_beyond_links(root: Path, batch: RepairBatch, kept: Sequence[str]) -> list[str]:
    """The entry pages the turn kept that it changed beyond adding link lines."""
    if batch.journey is None:
        return []
    entry_pages = set(batch.journey.entry_pages) - set(batch.page_paths)
    return [path for path in kept if path in entry_pages and not _adds_only_links(root, path)]


def _adds_only_links(root: Path, path: str) -> bool:
    current = root / path
    after = current.read_text(encoding="utf-8") if current.is_file() else ""
    return adds_only_links(committed_text(root, path), after)


def pages_to_stamp(root: Path, service: str, before: Snapshot, batch: RepairBatch) -> tuple[str, ...]:
    """The pages the turn changed that its batch may keep, but the entries page and the pages someone left uncommitted."""
    entries_page = entries_path(root, service).relative_to(root).as_posix()
    changed = book_changes(root, service, before)
    return tuple(
        path for path in changed if path != entries_page and path not in before.digests and _may_keep(service, batch, path)
    )


def stamp_repaired_pages(root: Path, pages: tuple[str, ...]) -> None:
    """Stamp each markdown page that is still on disk."""
    for page in pages:
        if page.endswith(".md") and (root / page).is_file():
            _ = stamp_page(root, root / FEATURES_DIR, page)
