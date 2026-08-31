"""Choose one flat authoring unit from the planning artifacts already on disk."""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from ostler import Ostler, registry
from ostler.model import Epic
from ostler.select import dag_order, epic_by_name
from workhorse_workflows.author.main.nodes._blueprint import blueprint
from workhorse_workflows.author.shared.paths import survey_repo_root
from workhorse_workflows.author.shared.roadmap import approved_roadmap
from workhorse_workflows.author.shared.schemas.main import AuthorStep
from workhorse_workflows.author.shared.story_split_receipt import story_split_review_current


def _ordered_epics(okf: Ostler, names: list[str]) -> list[Epic] | None:
    normalized = [registry.epic_slug(name) for name in names]
    if not names or len(set(normalized)) != len(normalized):
        return None
    epics = [epic_by_name(okf.graph, name) for name in names]
    if any(epic is None for epic in epics):
        return None
    return [epic for epic in epics if epic is not None]


def _story_graph_valid(epic: Epic) -> bool:
    """Whether story splitting has left a complete, local, acyclic graph."""
    if not epic.stories:
        return False
    slugs = [story.slug for story in epic.stories]
    if any(not slug for slug in slugs) or len(set(slugs)) != len(slugs):
        return False
    known = set(slugs)
    covered: set[str] = set()
    dependencies: dict[str, list[str]] = {}
    for story in epic.stories:
        if story.story_md is None or story.dependency_strays:
            return False
        if any(seed not in epic.seed_ids for seed in story.seed_items):
            return False
        if any(dependency not in known for dependency in story.dependencies):
            return False
        covered.update(story.seed_items)
        dependencies[story.slug] = story.dependencies
    if any(seed.active and seed.id not in covered for seed in epic.seeds):
        return False

    visited: set[str] = set()
    visiting: set[str] = set()

    def cyclic(slug: str) -> bool:
        if slug in visiting:
            return True
        if slug in visited:
            return False
        visiting.add(slug)
        if any(cyclic(dependency) for dependency in dependencies[slug]):
            return True
        visiting.remove(slug)
        visited.add(slug)
        return False

    return not any(cyclic(slug) for slug in slugs)


def _audit_current(story_path: Path | None) -> bool:
    if story_path is None:
        return False
    path = story_path
    receipt = path.parent / "audit-receipt.json"
    try:
        data = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    return (
        data.get("status") == "passed"
        and data.get("storyDigest") == hashlib.sha256(path.read_bytes()).hexdigest()
    )


@blueprint.node
def plan_author_step(
    logger: logging.Logger,
    blocked: tuple[str, ...] = (),
    repo_dir: str = "",
) -> AuthorStep:
    """Select exactly one next stage from the approved roadmap's current artifacts."""
    root = survey_repo_root(repo_dir)
    roadmap = approved_roadmap(root)
    okf = Ostler(root)
    matches = [milestone for milestone in okf.graph.milestones if roadmap in milestone.source_items]

    if len(matches) != 1 or matches[0].source_items != [roadmap]:
        reason = f"roadmap '{roadmap}' does not have exactly one sole-source milestone"
        logger.info(reason)
        return AuthorStep(kind="milestone", roadmap=roadmap, reason=reason)

    milestone = matches[0]
    epics = _ordered_epics(okf, milestone.epics)
    if epics is None:
        reason = f"milestone '{milestone.name}' has no valid ordered epic split"
        logger.info(reason)
        return AuthorStep(kind="epic-split", roadmap=roadmap, reason=reason)

    for epic in epics:
        if epic.epic_md is None or not epic.seeds:
            reason = f"epic '{epic.name}' needs epic documentation or researched seeds"
            logger.info(reason)
            return AuthorStep(
                kind="epic-author", roadmap=roadmap, epic=epic.name, reason=reason
            )

    for epic in epics:
        if not _story_graph_valid(epic) or not story_split_review_current(epic):
            reason = f"epic '{epic.name}' has no current semantically reviewed story graph"
            logger.info(reason)
            return AuthorStep(
                kind="story-split", roadmap=roadmap, epic=epic.name, reason=reason
            )

    for epic in epics:
        skipped = {
            item.split("/", 1)[1] for item in blocked if item.startswith(f"{epic.name}/")
        }
        report = okf.next_story_report(epic.name, need="author", skip=skipped)
        if report["state"] != "ready":
            for story in dag_order(epic):
                if story.slug in skipped or _audit_current(story.story_md):
                    continue
                return AuthorStep(
                    kind="story-author",
                    roadmap=roadmap,
                    epic=epic.name,
                    story=story.slug,
                    reason=f"story '{story.slug}' has no current passing audit receipt",
                )
            continue
        selected = report["story"] or {}
        slug = str(selected.get("slug", ""))
        reason = str(report["detail"])
        logger.info("story '%s' in epic '%s' needs current authoring", slug, epic.name)
        return AuthorStep(
            kind="story-author",
            roadmap=roadmap,
            epic=epic.name,
            story=slug,
            reason=reason,
        )

    reason = f"roadmap '{roadmap}' has a complete current planning graph"
    logger.info(reason)
    return AuthorStep(kind="finalize", roadmap=roadmap, reason=reason)


__all__ = ["plan_author_step"]
