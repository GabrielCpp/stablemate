"""Each node's text on a judged page, as a digest, so a later round can tell which nodes an edit touched."""
from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path

from ostler import markdown
from ostler.model import document_anchors
from ostler.stamp import unstamp_text


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def node_digests(root: Path, pages: Iterable[str]) -> dict[str, str]:
    """Each page, and each of its headed sections as `page#anchor`, keyed to a digest of its text. A section's text holds its subsections.

    A `code:` bullet's stamp is not text a judge weighs, so a stamp leaves every digest as it was.
    """
    digests: dict[str, str] = {}
    for page in pages:
        text = unstamp_text((root / page).read_text(encoding="utf-8"))
        digests[page] = _digest(text)
        doc = markdown.split(text)
        anchors = document_anchors(doc)
        for section in doc.walk_sections():
            anchor = anchors.get(section.line_start)
            if anchor:
                digests[f"{page}#{anchor}"] = _digest(section.text)
    return digests


def node_digests_on_pages_of(root: Path, nodes: Iterable[str]) -> dict[str, str]:
    """The digest of every node on each page one of `nodes` sits on, while that page still exists, judged this round or not."""
    pages = sorted({node.partition("#")[0] for node in nodes})
    return node_digests(root, (page for page in pages if (root / page).is_file()))
