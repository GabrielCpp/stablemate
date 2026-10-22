"""The acceptance walk: which of a story's criteria the plan's `## Acceptance Walk` covers."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from ostler import markdown

from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.dev import WalkCheck
from workhorse_workflows.kit import find_docs_root, find_repo_root

_AC_HEADING = re.compile(r"ac\s*(\d+)\b", re.IGNORECASE)


def criteria_count(story_text: str) -> int:
    """The top-level list items under the story's `## Acceptance Criteria`."""
    section = markdown.split(story_text).find_section("Acceptance Criteria")
    if section is None:
        return 0
    return sum(len(part.bullets) for part in section.walk())


def walked(plan_text: str) -> set[int]:
    """The criterion numbers the plan's `## Acceptance Walk` has a heading for."""
    section = markdown.split(plan_text).find_section("Acceptance Walk")
    if section is None:
        return set()
    found: set[int] = set()
    for part in section.walk():
        match = _AC_HEADING.match(part.title.strip()) if part is not section else None
        if match:
            found.add(int(match.group(1)))
    return found


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


@blueprint.node
def acceptance_walk(
    logger: logging.Logger,
    story_path: str = "",
    spec_dir: str = "",
    repo_dir: str = "",
) -> WalkCheck:
    """Which of the story's criteria the plan's acceptance walk leaves out."""
    story = Path(story_path)
    if not story.is_absolute():
        story = find_docs_root(repo_dir) / story
    spec = Path(spec_dir)
    if not spec.is_absolute():
        spec = find_repo_root(repo_dir) / spec
    criteria = criteria_count(_read(story))
    done = walked(_read(spec / "plan.md"))
    missing = [n for n in range(1, criteria + 1) if n not in done]
    logger.info("acceptance walk: %d of %d criteria walked", criteria - len(missing), criteria)
    return WalkCheck(criteria=criteria, missing=missing)


__all__ = ["acceptance_walk", "criteria_count", "walked"]
