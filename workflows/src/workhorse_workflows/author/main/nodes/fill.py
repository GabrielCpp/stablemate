"""File the ostler graph's epics, story splits and stories on the run's work list."""
from __future__ import annotations

import logging
from pathlib import Path

from ostler import Ostler, registry
from ostler.model import Epic
from ostler.select import dag_order, epic_by_name
from workhorse.pyflow import WorkflowFailed
from workhorse.worklist import WORK_FILE, JsonBackend, WorkItem, WorkList
from workhorse_workflows.author.main.nodes._blueprint import blueprint
from workhorse_workflows.author.pm.receipt import (
    MILESTONE_ARTIFACTS,
    epic_split_digest,
    pm_receipt_current,
    story_digest,
    story_split_digest,
)
from workhorse_workflows.author.shared.paths import survey_repo_root
from workhorse_workflows.author.shared.schemas.main import Defects, Filled

EPIC = "epic"
STORY_SPLIT = "story-split"
STORY = "story"
EPIC_SPLIT = "epic-split"
KINDS = (EPIC, STORY_SPLIT, STORY)
DONE = "done"
STORY_ORDER_STRIDE = 10_000


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


def _story_reviewed(story_path: Path | None) -> bool:
    if story_path is None:
        return False
    return pm_receipt_current(story_path.parent, STORY, story_digest(story_path))


def _split_reviewed(epic: Epic) -> bool:
    if epic.epic_md is None:
        return False
    return pm_receipt_current(epic.epic_md.parent, STORY_SPLIT, story_split_digest(epic))


def epic_id(epic: str) -> str:
    return f"{EPIC}:{epic}"


def story_split_id(epic: str) -> str:
    return f"{STORY_SPLIT}:{epic}"


def story_id(epic: str, story: str) -> str:
    return f"{epic}/{story}"


def _work(run_dir: str) -> WorkList:
    return WorkList(JsonBackend(Path(run_dir) / WORK_FILE))


def _ordered(okf: Ostler) -> list[Epic] | None:
    return _ordered_epics(okf, okf.approved_milestone().epics)


def _epic_written(epic: Epic) -> bool:
    return epic.epic_md is not None and bool(epic.seeds)


def _pending_stories(okf: Ostler, epic: Epic) -> set[str]:
    skipped: set[str] = set()
    while True:
        report = okf.next_story_report(epic.name, need="author", skip=skipped)
        if report["state"] != "ready":
            break
        slug = str((report["story"] or {}).get("slug", ""))
        if not slug or slug in skipped:
            break
        skipped.add(slug)
    return skipped | {
        story.slug for story in dag_order(epic) if not _story_reviewed(story.story_md)
    }


def _epic_items(epics: list[Epic]) -> list[WorkItem]:
    return [
        WorkItem(
            id=epic_id(epic.name),
            kind=EPIC,
            order=index,
            payload={"epic": epic.name},
            status=DONE if _epic_written(epic) else "",
        )
        for index, epic in enumerate(epics)
    ]


def _story_split_items(epics: list[Epic], finished: set[str]) -> list[WorkItem]:
    return [
        WorkItem(
            id=story_split_id(epic.name),
            kind=STORY_SPLIT,
            order=index,
            payload={"epic": epic.name},
            status=DONE
            if _story_graph_valid(epic) and _split_reviewed(epic)
            else "",
        )
        for index, epic in enumerate(epics)
        if epic_id(epic.name) in finished
    ]


def _story_items(okf: Ostler, epics: list[Epic], finished: set[str]) -> list[WorkItem]:
    items: list[WorkItem] = []
    for index, epic in enumerate(epics):
        if story_split_id(epic.name) not in finished:
            continue
        pending = _pending_stories(okf, epic)
        for position, story in enumerate(dag_order(epic)):
            items.append(
                WorkItem(
                    id=story_id(epic.name, story.slug),
                    kind=STORY,
                    order=index * STORY_ORDER_STRIDE + position,
                    payload={"epic": epic.name, "story": story.slug},
                    status="" if story.slug in pending else DONE,
                )
            )
    return items


@blueprint.node
def check_epic_split(logger: logging.Logger, repo_dir: str = "") -> Defects:
    """Whether the approved milestone already has a valid ordered epic split."""
    okf = Ostler(survey_repo_root(repo_dir))
    milestone = okf.approved_milestone()
    root = survey_repo_root(repo_dir)
    if _ordered_epics(okf, milestone.epics) is None:
        reason = f"milestone '{milestone.name}' has no valid ordered epic split"
        logger.info(reason)
        return Defects(ok=False, errors=reason)
    digest = epic_split_digest(root, milestone.path.relative_to(root).as_posix(), milestone.epics)
    if not pm_receipt_current(milestone.path.parent / MILESTONE_ARTIFACTS, EPIC_SPLIT, digest):
        reason = f"milestone '{milestone.name}' has no current PM pass of its epic split"
        logger.info(reason)
        return Defects(ok=False, errors=reason)
    return Defects(ok=True)


@blueprint.node
def fill_work(
    logger: logging.Logger,
    kind: str,
    run_dir: str,
    repo_dir: str = "",
) -> Filled:
    """File every item of *kind* the ostler graph holds, satisfied ones as done, skipping ids already filed."""
    if kind not in KINDS:
        raise WorkflowFailed(f"cannot fill unknown work kind '{kind}'")
    okf = Ostler(survey_repo_root(repo_dir))
    epics = _ordered(okf)
    if epics is None:
        raise WorkflowFailed("the approved milestone has no valid ordered epic split to fill from")
    work = _work(run_dir)
    finished = {item.id for item in work.items() if item.status == DONE}
    if kind == EPIC:
        wanted = _epic_items(epics)
    elif kind == STORY_SPLIT:
        wanted = _story_split_items(epics, finished)
    else:
        wanted = _story_items(okf, epics, finished)
    filed = {item.id for item in work.items()}
    fresh = [item for item in wanted if item.id not in filed]
    work.add(fresh)
    done = sum(1 for item in fresh if item.status == DONE)
    logger.info("filled %d %s items, %d already done", len(fresh), kind, done)
    return Filled(kind=kind, filed=len(fresh), done=done)


__all__ = ["check_epic_split", "fill_work"]
