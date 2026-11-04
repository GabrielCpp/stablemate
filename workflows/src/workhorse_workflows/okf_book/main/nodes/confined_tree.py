"""What a book turn does to the repo's working tree, as the nodes its flows call, so a dry run can stand in for each and leave the tree as it found it."""
from __future__ import annotations

import logging
from pathlib import Path

from ostler.stamp import stamp_page
from workhorse_workflows.okf_book.main.nodes.stale_citations import StaleFile, stale_files, stamp_spared
from workhorse_workflows.okf_book.shared.blueprint import blueprint
from workhorse_workflows.okf_book.shared.citations import cites_changed_file
from workhorse_workflows.okf_book.shared.confine import Snapshot, book_changes, changed_since, kept_changes, put_back_outside, restore, snapshot
from workhorse_workflows.okf_book.shared.entries import SERVICES_DIR


def _no_paths_in_dry_run(_logger: logging.Logger, *_args: object) -> tuple[str, ...]:
    return ()


def _no_change_in_dry_run(_logger: logging.Logger, *_args: object) -> None:
    return None


def _clean_tree_in_dry_run(_logger: logging.Logger, *_args: object) -> Snapshot:
    return Snapshot(digests={})


def _no_stale_files_in_dry_run(_logger: logging.Logger, *_args: object) -> tuple[StaleFile, ...]:
    return ()


def _nothing_cited_changed_in_dry_run(_logger: logging.Logger, *_args: object) -> bool:
    return False


def _nothing_stamped_in_dry_run(_logger: logging.Logger, *_args: object) -> tuple[tuple[str, ...], int]:
    return (), 0


@blueprint.node(stub=_no_change_in_dry_run)
def make_book_folder(logger: logging.Logger, root: Path, book_folder: str) -> None:
    """Make the folder the book's turn runs in. A dry run makes none."""
    del logger
    (root / book_folder).mkdir(parents=True, exist_ok=True)


@blueprint.node(stub=_clean_tree_in_dry_run)
def tree_snapshot(logger: logging.Logger, root: Path) -> Snapshot:
    """Record the working tree before a turn. A dry run reads no tree and holds a clean one."""
    del logger
    return snapshot(root)


@blueprint.node(stub=_no_paths_in_dry_run)
def book_pages_changed(logger: logging.Logger, root: Path, service: str, before: Snapshot) -> tuple[str, ...]:
    """The paths inside the service's book the turn changed. A dry run changed none."""
    del logger
    return book_changes(root, service, before)


@blueprint.node(stub=_no_paths_in_dry_run)
def pages_kept(logger: logging.Logger, root: Path, service: str, before: Snapshot, run_dir: Path) -> tuple[str, ...]:
    """The paths the turn changed that the book keeps. A dry run changed none."""
    del logger
    return kept_changes(root, service, before, run_dir)


@blueprint.node(stub=_no_paths_in_dry_run)
def put_back_strays(logger: logging.Logger, root: Path, service: str, before: Snapshot, run_dir: Path) -> tuple[str, ...]:
    """Restore what the turn changed outside its book, and return those paths. A dry run restores nothing."""
    del logger
    return put_back_outside(root, service, before, run_dir)


@blueprint.node(stub=_no_paths_in_dry_run)
def restore_tree(logger: logging.Logger, root: Path, before: Snapshot) -> tuple[str, ...]:
    """Put back everything a turn that changes no file changed anyway. A dry run restores nothing."""
    del logger
    return restore(root, changed_since(root, before), before)


@blueprint.node(stub=_no_change_in_dry_run)
def stamp_changed_pages(logger: logging.Logger, root: Path, service: str, before: Snapshot) -> None:
    """Stamp every page the turn changed in its book. A dry run stamps none."""
    del logger
    for page in book_changes(root, service, before):
        if page.endswith(".md") and (root / page).is_file():
            _ = stamp_page(root, root / SERVICES_DIR, page)


@blueprint.node(stub=_no_stale_files_in_dry_run)
def stale_book_files(logger: logging.Logger, root: Path, service: str) -> tuple[StaleFile, ...]:
    """Every changed file the service's book cites. A dry run reads no book and finds none."""
    del logger
    return stale_files(root, service)


@blueprint.node(stub=_nothing_cited_changed_in_dry_run)
def book_cites_changed_file(logger: logging.Logger, root: Path, service: str) -> bool:
    """Whether the service's book cites a file that changed since its stamp. A dry run reads no book and finds none."""
    del logger
    return cites_changed_file(root, service)


@blueprint.node(stub=_nothing_stamped_in_dry_run)
def stamp_spared_pages(logger: logging.Logger, root: Path, spared: tuple[tuple[str, str], ...]) -> tuple[tuple[str, ...], int]:
    """Stamp each citation its file's change spares, and return the pages and the count. A dry run stamps none."""
    del logger
    return stamp_spared(root, spared)


__all__ = [
    "book_cites_changed_file",
    "book_pages_changed",
    "make_book_folder",
    "pages_kept",
    "put_back_strays",
    "restore_tree",
    "stale_book_files",
    "stamp_changed_pages",
    "stamp_spared_pages",
    "tree_snapshot",
]
