"""The books above one service: prose pages, one markdown file each, at three levels. The company
book is `company/` and a team book is `teams/<team>/`, both in the artifacts dir. A repository reads the
team its agents.yml names, and the artifacts folder reads every team. The product book is
`products/<product>/` in the book root of the start, the artifacts dir or its worktree on the start's branch, or `product/` beside `services/` when the repository keeps its book. A page has a `date:` line, optional `sources:` and `status:` lines, a
blank line, then prose whose first line is its statement."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ostler._vendor.stablemate_core import books
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
        return f"{self.kind} {self.name}" if self.name else self.kind


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


def product_levels(start: Path) -> list[Level]:
    if books.book_in_repo(start):
        return [Level("product", "", os.path.join(str(books.book_settings(start).folder), "product"), "product")]
    name = books.book_product(start)
    if name is not None:
        folder = books.product_folder(start)
        if folder is not None:
            return [Level("product", name, str(folder), f"products/{name}")]
    folder = str(books.book_home(start) / "products")
    names = sorted(n for n in os.listdir(folder) if os.path.isdir(os.path.join(folder, n))) if os.path.isdir(folder) else []
    return [Level("product", n, os.path.join(folder, n), f"products/{n}") for n in names]


def levels(root: str, start: str | None = None) -> list[Level]:
    artifacts = str(core_config.resolve_artifacts_dir())
    origin = Path(start if start is not None else os.getcwd())
    found = [Level("company", "", os.path.join(artifacts, "company"), "company")]
    for team in teams_of(root, origin, artifacts):
        found.append(Level("team", team, os.path.join(artifacts, "teams", team), f"teams/{team}"))
    return found + product_levels(origin)


def teams_of(root: str, origin: Path, artifacts: str) -> list[str]:
    """The team the code at `origin` names, or every team when `origin` is the artifacts folder."""
    if books.namespaced(origin):
        folder = os.path.join(artifacts, "teams")
        return sorted(n for n in os.listdir(folder) if os.path.isdir(os.path.join(folder, n))) if os.path.isdir(folder) else []
    team = books.book_settings(origin).team or team_of(root)
    return [team] if team else []


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
