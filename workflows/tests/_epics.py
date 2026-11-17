"""Where a test's epics live: the per-test artifacts dir, never the repository."""

from __future__ import annotations

import os
from pathlib import Path


def epics_root() -> Path:
    return Path(os.environ["STABLEMATE_ARTIFACTS_DIR"]).resolve() / "epics"


def write_epic_prose(epic_md: Path) -> None:
    """Give *epic_md* a paragraph under every section the epic contract requires, above `## Seeds`."""
    from ostler import registry

    text = epic_md.read_text(encoding="utf-8")
    if "## User Outcome" in text:
        return
    sections = "".join(
        f"## {spec.heading}\n\nWhat the epic holds to for {spec.heading.lower()}.\n\n"
        for spec in registry.EPIC_SECTIONS
    )
    epic_md.write_text(text.replace("## Seeds", sections + "## Seeds", 1), encoding="utf-8")
