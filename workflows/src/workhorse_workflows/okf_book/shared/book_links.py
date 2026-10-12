"""Links from a page of another book into the service's book.

A writer that moves or removes a page of its book points another book's links at the page that now
holds the subject, through `relink`. Such an edit changes only link targets that land in its own
book. Each link from another book that still lands on a missing page or anchor of the book is a
problem of the book.
"""
from __future__ import annotations

import posixpath
import re
from dataclasses import replace

from ostler.doctor import Report
from ostler.finding import Finding
from workhorse_workflows.okf_book.shared.entries import FEATURES_DIR

_LINK_TARGET = re.compile(r"(\]\()([^)\s]*)")
_INTO_BOOK = "\0"
LINK_CODES = frozenset({"dangling-link", "unresolved-relation", "missing-anchor"})


def in_book(service: str, path: str) -> bool:
    """True for a path in the service's book."""
    return path.startswith(f"{(FEATURES_DIR / service).as_posix()}/")


def lands_in_book(service: str, page: str, href: str) -> bool:
    """True when *href*, written on *page*, resolves to a path in the service's book."""
    target = href.partition("#")[0]
    if not target or ":" in target or target.startswith("/"):
        return False
    return in_book(service, posixpath.normpath(posixpath.join(posixpath.dirname(page), target)))


def relinked(service: str, page: str, text: str, old: str, new: str) -> tuple[str, int]:
    """*text* of *page* with each link that lands on *old* pointed at *new*, and how many links changed.

    *old* and *new* are paths in the service's book relative to its folder, each with an optional
    `#anchor`. An *old* with no anchor matches a link with any anchor, and a *new* with no anchor
    keeps the link's own.
    """
    book = (FEATURES_DIR / service).as_posix()
    old_path, _, old_anchor = old.partition("#")
    new_path, _, new_anchor = new.partition("#")
    old_full = posixpath.normpath(posixpath.join(book, old_path))
    new_href = posixpath.relpath(posixpath.normpath(posixpath.join(book, new_path)), posixpath.dirname(page))
    changed = 0

    def swap(match: re.Match[str]) -> str:
        nonlocal changed
        target, _, anchor = match.group(2).partition("#")
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(page), target)) if target else ""
        if resolved != old_full or (old_anchor and anchor != old_anchor):
            return match.group(0)
        changed += 1
        kept = new_anchor or anchor
        return match.group(1) + new_href + (f"#{kept}" if kept else "")

    return _LINK_TARGET.sub(swap, text), changed


def without_book_targets(service: str, page: str, text: str) -> str:
    """*text* with each link target that lands in the service's book replaced by one placeholder."""
    return _LINK_TARGET.sub(
        lambda match: match.group(1) + (_INTO_BOOK if lands_in_book(service, page, match.group(2)) else match.group(2)),
        text,
    )


def retargets_only(service: str, page: str, before: str, after: str) -> bool:
    """True when *after* differs from *before* only in link targets that land in the service's book, on both sides."""
    return before != after and without_book_targets(service, page, before) == without_book_targets(service, page, after)


def _href(finding: Finding) -> str:
    return (finding.ref or "").removeprefix(f"{finding.path}:{finding.line}:")


def inbound_broken(report: Report, service: str) -> tuple[Finding, ...]:
    """Each broken link from a page outside the service's book that lands in the book, suggesting the writer retarget it."""
    retarget = f"Point it at the page of the {service} book that now holds the subject, with the ostler command's `relink`."
    return tuple(
        replace(finding, suggestion=retarget)
        for finding in report.findings
        if finding.code in LINK_CODES
        and finding.path
        and not in_book(service, finding.path)
        and lands_in_book(service, finding.path, _href(finding))
    )
