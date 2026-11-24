"""The hashes that bind a run's decisions to the bytes they were made about."""
from __future__ import annotations

import hashlib

from ostler import markdown, registry
from workhorse_workflows.kit.paths import artifacts_root


def milestone_body_digest(milestone_path: str) -> str:
    """The sha256 of the milestone body the owner writes, without the `## Epics` section ostler writes."""
    text = (artifacts_root() / milestone_path).read_text(encoding="utf-8")
    document = markdown.split(text)
    lines = document.body.split("\n")
    section = document.find_section(registry.MILESTONE_EPICS_HEADING)
    if section is not None:
        del lines[section.line_start:section.line_end]
    owned = "\n".join(lines).rstrip("\n") + "\n"
    return hashlib.sha256(owned.encode("utf-8")).hexdigest()


__all__ = ["milestone_body_digest"]
