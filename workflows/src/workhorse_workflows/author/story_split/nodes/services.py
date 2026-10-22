"""Write each story's `services:` from the seeds it covers."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from ostler import Ostler, markdown
from ostler.select import epic_by_name
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.author.shared.paths import survey_repo_root
from workhorse_workflows.author.story_split.nodes._blueprint import blueprint
from workhorse_workflows.author.story_split.schemas import StoryServices

_SERVICES_KEY = re.compile(r"^services\s*:")
_CONTINUATION = re.compile(r"^(\s+|-\s)")


def _with_services(raw: str, services: list[str]) -> str:
    kept: list[str] = []
    skipping = False
    for line in raw.splitlines():
        if _SERVICES_KEY.match(line):
            skipping = True
            continue
        if skipping and _CONTINUATION.match(line):
            continue
        skipping = False
        kept.append(line)
    kept.append(f"services: [{', '.join(services)}]")
    return "\n".join(kept) + "\n"


def _write_services(story_md: Path, services: list[str]) -> None:
    doc = markdown.split(story_md.read_text(encoding="utf-8"))
    if not doc.has_frontmatter:
        raise WorkflowFailed(f"{story_md} has no frontmatter to write `services:` into")
    doc.raw_frontmatter = _with_services(doc.raw_frontmatter, services)
    story_md.write_text(doc.render(), encoding="utf-8")


@blueprint.node
def derive_story_services(
    logger: logging.Logger,
    epic: str,
    repo_dir: str = "",
) -> StoryServices:
    """Each story's services are the sorted union of the services of the seeds it covers."""
    root = survey_repo_root(repo_dir)
    found = epic_by_name(Ostler(root).graph, epic)
    if found is None:
        raise WorkflowFailed(f"cannot derive story services: no epic named '{epic}'")
    seed_services = {seed.id: seed.services for seed in found.seeds}
    derived: dict[str, list[str]] = {}
    for story in found.stories:
        if story.story_md is None:
            continue
        union = sorted({
            service
            for seed_id in story.seed_items
            for service in seed_services.get(seed_id, ())
        })
        derived[story.slug] = union
        if tuple(union) != story.services:
            _write_services(story.story_md, union)
    logger.info("derived services for %d story(ies) of epic %s", len(derived), epic)
    return StoryServices(epic=epic, services=derived)


__all__ = ["derive_story_services"]
