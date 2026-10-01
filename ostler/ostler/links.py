"""Path-link resolution for the OKF UI profile (§6.1)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ostler.model import Graph, document_anchors, read_doc

_SKIP_PREFIXES = ("http://", "https://", "mailto:", "tel:", "ftp://")


@dataclass
class LinkTarget:
    href: str
    path: Path
    anchor: str
    file_exists: bool
    anchor_exists: bool
    node_id: str

    @property
    def resolved(self) -> bool:
        return self.file_exists and (not self.anchor or self.anchor_exists)


def is_doc_link(href: str) -> bool:
    """True when *href* is a repo-relative doc link ostler should resolve (not a URL / code ref)."""
    href = href.strip()
    if not href or href.startswith(_SKIP_PREFIXES) or "::" in href:
        return False
    return True


class LinkResolver:
    """Resolves links, caching each target file's heading-anchor set for the run."""

    def __init__(self, graph: Graph) -> None:
        self.graph = graph
        self._anchors: dict[Path, set[str]] = {}
        self._files: dict[tuple[Path, str], tuple[Path, bool, str]] = {}
        self._dirs: dict[Path, Path] = {}
        self._root_prefix: str | None = None

    def anchors(self, path: Path) -> set[str]:
        if path not in self._anchors:
            self._anchors[path] = self._compute_anchors(path)
        return self._anchors[path]

    def _compute_anchors(self, path: Path) -> set[str]:
        try:
            doc = read_doc(path)
        except OSError:
            return set()
        return set(document_anchors(doc).values())

    def _settle_file(self, source: Path, path_part: str) -> tuple[Path, bool, str]:
        target = source if path_part == "" else self._real(source.parent / path_part)
        return target, target.is_file(), self._rel(target)

    def _real(self, joined: Path) -> Path:
        """``joined.resolve()``, with each directory resolved once per run instead of once per link."""
        if joined.name in ("", ".", ".."):
            return joined.resolve()
        if joined.parent not in self._dirs:
            self._dirs[joined.parent] = joined.parent.resolve()
        target = self._dirs[joined.parent] / joined.name
        return target.resolve() if target.is_symlink() else target

    def _rel(self, target: Path) -> str:
        """*target* relative to the graph root in posix form, or its absolute posix form when outside it."""
        if self._root_prefix is None:
            self._root_prefix = str(self.graph.root).rstrip(os.sep) + os.sep
        text = str(target)
        if text.startswith(self._root_prefix):
            return text[len(self._root_prefix):].replace(os.sep, "/")
        if target == self.graph.root:
            return "."
        return target.as_posix()

    def resolve(self, source: Path, href: str) -> LinkTarget | None:
        """Resolve *href* found in *source*."""
        if not is_doc_link(href):
            return None
        path_part, _, anchor = href.strip().partition("#")
        key = (source if path_part == "" else source.parent, path_part)
        if key not in self._files:
            self._files[key] = self._settle_file(source, path_part)
        target, file_exists, rel = self._files[key]
        anchor_exists = bool(anchor) and file_exists and anchor in self.anchors(target)
        node_id = f"{rel}#{anchor}" if anchor else rel
        return LinkTarget(href=href.strip(), path=target, anchor=anchor,
                          file_exists=file_exists, anchor_exists=anchor_exists, node_id=node_id)
