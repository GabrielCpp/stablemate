"""`ostler doctor`'s check that no book page outgrows what one writer can read and rewrite in a turn."""

from __future__ import annotations

from ostler import registry
from ostler.finding import Finding
from ostler.model import Graph
from ostler.pages import files_in_book

PAGE_SIZE_LIMIT = 64 * 1024


def check_page_size(graph: Graph, f: list[Finding]) -> None:
    """Each page of the book stays within `PAGE_SIZE_LIMIT` bytes."""
    froot = graph.doc_roots.get("features")
    if froot is None or not froot.is_dir():
        return
    for path in files_in_book(froot):
        if path.name in registry.RESERVED_FILES:
            continue
        size = path.stat().st_size
        if size <= PAGE_SIZE_LIMIT:
            continue
        rel = path.resolve().relative_to(graph.root.resolve()).as_posix()
        f.append(Finding(
            "error", "page-too-large",
            f"{rel}: the page holds {size // 1024} KiB, past the {PAGE_SIZE_LIMIT // 1024} KiB a "
            f"writer can read and rewrite in one turn, so each edit to it truncates or drops a "
            f"part. The run moves its largest sections onto fragment pages before the next lap; "
            f"by hand, `ostler edit carve-fragments {rel} --write`",
            path=rel, line=1, ref=rel))
