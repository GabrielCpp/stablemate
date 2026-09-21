"""Path-link resolution for the OKF UI profile (§6.1)."""

from __future__ import annotations

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
        target = source if path_part == "" else (source.parent / path_part).resolve()
        try:
            rel = target.relative_to(self.graph.root).as_posix()
        except ValueError:
            rel = target.as_posix()
        return target, target.is_file(), rel

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
