"""A service's `entries.md`: the root of its book, one link per entry point, written only by code."""
from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path

FEATURES_DIR = Path("docs") / "features"
ENTRIES_NAME = "entries.md"

_LINK = re.compile(r"^\s*[-*]\s+\[(?P<title>[^\]]+)\]\((?P<target>[^)\s]+)\)\s*$")


@dataclass(frozen=True, slots=True)
class EntryLink:
    """One list item of an entries page: a title and a target relative to the service's book."""

    title: str
    target: str

    @property
    def page(self) -> str:
        """The target without its anchor: the page file the link lands on."""
        return self.target.partition("#")[0]

    def render(self) -> str:
        return f"- [{self.title}]({self.target})"


def book_dir(root: Path, service: str) -> Path:
    return root / FEATURES_DIR / service


def entries_path(root: Path, service: str) -> Path:
    return book_dir(root, service) / ENTRIES_NAME


def services(root: Path) -> tuple[str, ...]:
    """Every service whose book has an entries page, by name."""
    features = root / FEATURES_DIR
    if not features.is_dir():
        return ()
    return tuple(sorted(d.name for d in features.iterdir() if (d / ENTRIES_NAME).is_file()))


def read_entries(root: Path, service: str) -> tuple[EntryLink, ...]:
    path = entries_path(root, service)
    if not path.is_file():
        return ()
    found: list[EntryLink] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _LINK.match(line)
        if match:
            found.append(EntryLink(match.group("title"), match.group("target")))
    return tuple(found)


def links_to_deleted(root: Path, service: str, changed: Collection[str]) -> tuple[EntryLink, ...]:
    """The links of the service's entries page to a page of *changed*, repo-relative paths, that is gone from disk."""
    book = book_dir(root, service)
    return tuple(
        link for link in read_entries(root, service) if link.page and _repo_path(root, book / link.page) in changed and not (book / link.page).is_file()
    )


def _repo_path(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def drop_links(root: Path, service: str, links: Collection[EntryLink]) -> None:
    """Remove the line of each of *links* from the service's entries page."""
    path = entries_path(root, service)
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    _ = path.write_text("".join(line for line in lines if _entry_link(line) not in links), encoding="utf-8")


def _entry_link(line: str) -> EntryLink | None:
    match = _LINK.match(line.rstrip("\n"))
    return EntryLink(match.group("title"), match.group("target")) if match else None
