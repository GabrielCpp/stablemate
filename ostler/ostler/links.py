"""Path-link resolution for the OKF UI profile (§6.1).

``References.links`` are *extracted* by ``markdown.py`` but never *resolved*. This module resolves
a ``[text](path)`` / ``[text](path#anchor)`` link against the filesystem: the ``path`` relative to
the source file, and the ``#anchor`` against the target file's heading anchors. That is what turns
``parent:`` / ``extends:`` / ``on:`` / ``steps:`` bullets from decoration into load-bearing graph
edges — walked by ``trace`` and checked by ``doctor`` (dangling-link / missing-anchor).

A link's ``#anchor`` resolves against *every* heading in the target (GitHub-style), not only typed
``### id`` section nodes, so an intra-doc jump to a prose ``## Heading`` resolves too.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ostler import markdown
from ostler.model import Graph, anchor_of

_SKIP_PREFIXES = ("http://", "https://", "mailto:", "tel:", "ftp://")


@dataclass
class LinkTarget:
    href: str
    path: Path              # the resolved file (may not exist)
    anchor: str             # the #fragment ("" if none)
    file_exists: bool
    anchor_exists: bool     # only meaningful when anchor and file_exists
    node_id: str            # the target's UI-node identity: "<repo-rel>" or "<repo-rel>#<anchor>"

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

    def anchors(self, path: Path) -> set[str]:
        if path not in self._anchors:
            self._anchors[path] = self._compute_anchors(path)
        return self._anchors[path]

    def _compute_anchors(self, path: Path) -> set[str]:
        try:
            doc = markdown.split(path.read_text(encoding="utf-8"))
        except OSError:
            return set()
        return {anchor_of(s.title) for s in doc.walk_sections() if s.title.strip()}

    def resolve(self, source: Path, href: str) -> LinkTarget | None:
        """Resolve *href* found in *source*. None if it isn't a doc link (URL / code ref)."""
        if not is_doc_link(href):
            return None
        path_part, _, anchor = href.strip().partition("#")
        target = source if path_part == "" else (source.parent / path_part).resolve()
        file_exists = target.is_file()
        anchor_exists = bool(anchor) and file_exists and anchor in self.anchors(target)
        try:
            rel = target.relative_to(self.graph.root).as_posix()
        except ValueError:
            rel = target.as_posix()
        node_id = f"{rel}#{anchor}" if anchor else rel
        return LinkTarget(href=href.strip(), path=target, anchor=anchor,
                          file_exists=file_exists, anchor_exists=anchor_exists, node_id=node_id)
