"""The business pages: rules above any one service, one markdown file each under `business/` beside
`services/`. A page has a `date:` line, optional `sources:`, a blank line, then prose whose first line
is its statement."""

from __future__ import annotations

import os
from typing import Any

from ostler.book import decisions
from ostler.book.index import book_root

FOLDER = "business"


def load(root: str) -> list[decisions.Decision]:
    folder = os.path.join(root, FOLDER)
    if not os.path.isdir(folder):
        return []
    return [decisions.parse(os.path.join(folder, name)) for name in sorted(os.listdir(folder)) if name.endswith(".md")]


def statement(page: decisions.Decision) -> str:
    return next((line.strip() for line in page.body.splitlines() if line.strip()), "")


def problems(page: decisions.Decision) -> list[str]:
    found = [] if page.date else ["has no date: line"]
    return found + ([] if statement(page) else ["has an empty body"])


def cmd_business(args: Any, root: str | None = None) -> int:
    root = root if root is not None else book_root(os.getcwd())
    if root is None:
        raise SystemExit("no services directory above the current directory")
    pages = load(root)
    if args.check:
        broken = [(page, problems(page)) for page in pages]
        for page, found in broken:
            if found:
                print(f"{FOLDER}/{page.slug}.md {' and '.join(found)}")
        return 1 if any(found for _, found in broken) else 0
    for page in pages:
        print(f"{page.slug}  {page.date}  {statement(page)}")
    return 0
