"""The scope each epic holds, read from its epic.md."""
from __future__ import annotations

from pathlib import Path

from ostler import markdown


def subsection_ids(text: str, heading: str) -> set[str]:
    """The `### <id>` titles directly under the `## <heading>` section of an epic.md."""
    ids: set[str] = set()
    for root in markdown.split(text or "").sections:
        for section in root.walk():
            if section.level == 2 and section.title.strip().lower() == heading.lower():
                ids.update(c.title.strip() for c in section.children if c.level == 3)
    return ids


def epic_scopes(epics_path: Path) -> dict[str, tuple[set[str], set[str]]]:
    """Each epic folder's seed ids and story slugs, from its epic.md."""
    scopes: dict[str, tuple[set[str], set[str]]] = {}
    for epic_md in sorted(epics_path.glob("*/epic.md")):
        text = epic_md.read_text(encoding="utf-8")
        scopes[epic_md.parent.name] = (subsection_ids(text, "Seeds"), subsection_ids(text, "Stories"))
    return scopes


__all__ = ["epic_scopes", "subsection_ids"]
