"""A service's `entries.md`: the root of its book, one link per entry point, written only by code."""
from __future__ import annotations

import re
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
