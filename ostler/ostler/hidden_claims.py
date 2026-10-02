"""`ostler doctor`'s check that no claim sits inside an HTML comment, where no check reads it and no reader sees it."""

from __future__ import annotations

import re

from ostler import markdown, registry
from ostler.finding import Finding
from ostler.model import Graph
from ostler.pages import files_in_book

_BULLET = re.compile(r"^\s*[-*+]\s+([a-z][a-z -]*?):")


def _claim_keys() -> frozenset[str]:
    keys = frozenset(registry.RELATION_KEYS)
    for uitype in registry.UI_TYPES:
        keys |= registry.declared_keys(uitype.name)
    return keys


def _hidden(comment: str, keys: frozenset[str]) -> list[str]:
    return [m.group(1) for line in comment.split("\n") if (m := _BULLET.match(line)) and m.group(1) in keys]


def check_hidden_claims(graph: Graph, f: list[Finding]) -> None:
    """Each comment on a book page holds no bullet a page would read as a claim."""
    froot = graph.doc_roots.get("features")
    if froot is None or not froot.is_dir():
        return
    keys = _claim_keys()
    for path in files_in_book(froot):
        if path.name in registry.RESERVED_FILES:
            continue
        rel = path.resolve().relative_to(graph.root.resolve()).as_posix()
        for start, comment in markdown.comment_blocks(path.read_text(encoding="utf-8")):
            found = _hidden(comment, keys)
            if not found:
                continue
            named = ", ".join(sorted(set(found)))
            f.append(Finding(
                "error", "hidden-claim",
                f"{rel}:{start + 1}: a comment holds {len(found)} claim bullet(s) ({named}), which no "
                f"check runs and no reader sees, so the page reads as if the claim were never made. "
                f"Restore the claim as a bullet the page states, or delete it",
                path=rel, line=start + 1, ref=rel))
