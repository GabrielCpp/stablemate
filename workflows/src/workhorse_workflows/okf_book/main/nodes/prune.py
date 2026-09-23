"""Pages whose source is gone: each is found first, then deleted in its own commit."""
from __future__ import annotations

from pathlib import Path

from workhorse_workflows.kit import commit_paths, list_tracked_files
from workhorse_workflows.okf_book.shared.citations import book_pages, page_citations
from workhorse_workflows.okf_book.shared.entries import (
    FEATURES_DIR,
    book_dir,
    entries_path,
    read_entries,
    write_entries,
)


class PruneError(RuntimeError):
    """A deleted page is still tracked after its commit."""


def is_orphaned(root: Path, page: Path) -> bool:
    """True when the page cites at least one file, and every file it cites is gone."""
    cited = {c.path for c in page_citations(page)}
    return bool(cited) and not any((root / path).is_file() for path in cited)


def orphaned_pages(root: Path, service: str) -> tuple[str, ...]:
    """Every page of the service's book whose source is gone, repo-relative."""
    entries = entries_path(root, service)
    return tuple(
        page.relative_to(root).as_posix()
        for page in book_pages(root, service)
        if page != entries and is_orphaned(root, page)
    )


def _service(page: str) -> str:
    return Path(page).relative_to(FEATURES_DIR).parts[0]


def _drop_links(root: Path, service: str, page: Path) -> None:
    """Remove the entries links landing on `page`, leaving the entries page untouched when none do."""
    target = page.relative_to(book_dir(root, service)).as_posix()
    links = read_entries(root, service)
    kept = tuple(link for link in links if link.page != target)
    if kept != links:
        _ = write_entries(root, service, kept)


def remove_page(root: Path, page: str) -> tuple[str, ...]:
    """Delete one orphaned page and its entries links, and name every path the deletion commits."""
    service = _service(page)
    path = root / page
    path.unlink(missing_ok=True)
    _drop_links(root, service, path)
    entries = entries_path(root, service)
    return (page, entries.relative_to(root).as_posix()) if entries.is_file() else (page,)


def commit_removal(root: Path, page: str, paths: tuple[str, ...]) -> bool:
    """Commit a removed page, and refuse to move on while git still tracks it. A second call finds it done."""
    committed = commit_paths(root, f"docs({_service(page)}): delete {Path(page).stem}, its source is gone", *paths)
    if list_tracked_files(root, page):
        raise PruneError(f"{page} is deleted but still tracked")
    return committed
