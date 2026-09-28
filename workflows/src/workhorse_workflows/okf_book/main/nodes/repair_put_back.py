"""Which book pages a repair turn changed that its batch may keep, and the stamp on those it keeps.

Each batch owns the pages it is sent. A batch with a page no other page reaches, or with an endpoint
on no flow, also owns the journey pages the repair planned: the pages the entries page links, the flow
pages, and a new page in the flow folder, since the fix for either goes there. On a page the entries
page links it may only add link lines. Every other page the turn changed goes back: the entries page,
which only code writes, a page someone left uncommitted, and a page an earlier batch closed.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ostler.stamp import stamp_page
from workhorse_workflows.okf_book.main.nodes.journey import adds_only_links
from workhorse_workflows.okf_book.main.nodes.repair_batches import RepairBatch
from workhorse_workflows.okf_book.shared.confine import Snapshot, absent_from_head, book_changes, committed_text
from workhorse_workflows.okf_book.shared.entries import FEATURES_DIR, entries_path


@dataclass(frozen=True, slots=True)
class TurnChanges:
    """The book pages a repair turn changed: those its batch may keep, and those code puts back."""

    entries: str
    kept: tuple[str, ...]
    unowned: tuple[str, ...]


def turn_changes(root: Path, service: str, before: Snapshot, batch: RepairBatch, closed_pages: tuple[str, ...]) -> TurnChanges:
    """Split the book pages the turn changed into those the batch owns and those it does not."""
    entries = entries_path(root, service).relative_to(root).as_posix()
    changed = book_changes(root, service, before)
    created = absent_from_head(root, changed)
    unowned = tuple(
        path
        for path in changed
        if path == entries or path in before.digests or path in closed_pages or not batch.owns(path, created)
    )
    return TurnChanges(entries, tuple(path for path in changed if path not in unowned), unowned)


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
    """The pages the turn changed that its batch owns, but the entries page and the pages someone left uncommitted."""
    entries = entries_path(root, service).relative_to(root).as_posix()
    changed = book_changes(root, service, before)
    created = absent_from_head(root, changed)
    return tuple(path for path in changed if path != entries and path not in before.digests and batch.owns(path, created))


def stamp_repaired_pages(root: Path, pages: tuple[str, ...]) -> None:
    """Stamp each markdown page that is still on disk."""
    for page in pages:
        if page.endswith(".md") and (root / page).is_file():
            _ = stamp_page(root, root / FEATURES_DIR, page)
