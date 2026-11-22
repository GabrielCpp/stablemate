"""The books above one service: prose pages, one markdown file each, at three levels. The company
book is `company/` and a team book is `teams/<team>/`, both in the artifacts dir. The product book is
`product/` beside `services/`. A page has a `date:` line, optional `sources:` and `status:` lines, a
blank line, then prose whose first line is its statement."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ostler._vendor.stablemate_core import config as core_config
from ostler.book import decisions
from ostler.manifest import read_manifest

LEVELS = ("company", "team", "product")


@dataclass(frozen=True)
class Level:
    kind: str
    name: str
    folder: str
    address: str

    @property
    def heading(self) -> str:
        return f"team {self.name}" if self.kind == "team" else self.kind


@dataclass(frozen=True)
class Page:
    slug: str
    level: Level
    date: str
    status: str
    body: str
    offset: int
    header: tuple[tuple[int, str], ...]

    @property
    def path(self) -> str:
        return f"{self.level.address}/{self.slug}.md"

    def statement(self) -> str:
        return next((line.strip() for line in self.body.splitlines() if line.strip()), "")

    def superseded(self) -> bool:
        return self.status.lower().startswith("superseded")

    def searchable(self) -> list[tuple[int, str]]:
        return [*self.header, *((self.offset + n, text) for n, text in enumerate(self.body.splitlines(), 1))]


def team_of(root: str) -> str:
    from ostler.model import find_root

    manifest = read_manifest(find_root(Path(root)))
    return (manifest.book.team if manifest is not None else None) or ""


def levels(root: str) -> list[Level]:
    artifacts = str(core_config.resolve_artifacts_dir())
    found = [Level("company", "", os.path.join(artifacts, "company"), "company")]
    team = team_of(root)
    if team:
        found.append(Level("team", team, os.path.join(artifacts, "teams", team), f"teams/{team}"))
    found.append(Level("product", "", os.path.join(root, "product"), "product"))
    return found


def parse(path: str, level: Level) -> Page:
    fields, header, body, offset = decisions.read_page(path, ("sources", "status"))
    return Page(os.path.basename(path).removesuffix(".md"), level, fields.get("date", ""), fields.get("status", ""), body, offset, header)


def load(level: Level) -> list[Page]:
    if not os.path.isdir(level.folder):
        return []
    return [parse(os.path.join(level.folder, name), level) for name in sorted(os.listdir(level.folder)) if name.endswith(".md")]


def problems(page: Page) -> list[str]:
    found = [] if page.date else ["has no date: line"]
    return found + ([] if page.statement() else ["has an empty body"])


def cmd_pages(args: Any, root: str | None = None) -> int:
    from ostler.book.index import book_root

    root = root if root is not None else book_root(os.getcwd())
    if root is None:
        raise SystemExit("no services directory above the current directory")
    chosen = [level for level in levels(root) if args.level in (None, level.kind)]
    pages = [page for level in chosen for page in load(level)]
    if args.check:
        broken = [(page, problems(page)) for page in pages]
        for page, found in broken:
            if found:
                print(f"{page.path} {' and '.join(found)}")
        return 1 if any(found for _, found in broken) else 0
    for page in pages:
        status = f"  {page.status}" if page.status else ""
        print(f"{page.level.kind}  {page.slug}  {page.date}{status}  {page.statement()}")
    return 0
