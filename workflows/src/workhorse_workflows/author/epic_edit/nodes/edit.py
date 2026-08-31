"""Snapshot, validate, apply, and verify one epic graph edit."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from ostler import Ostler, markdown, registry
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.author.epic_edit.nodes._blueprint import blueprint
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.schemas import (
    AppliedEpicEdit,
    Defects,
    EditIntent,
    EpicEditPlan,
    EpicSnapshot,
    MilestoneSnapshot,
    SeedSnapshot,
    StoryChoice,
    StorySnapshot,
)

_INACTIVE_SEED_STATUSES = {"resolved", "dropped", "deferred"}
_REQUIRED_EPIC_SECTIONS = (
    "User Outcome",
    "User Journeys",
    "Delivered Experience",
    "Guardrails",
    "Non-Goals",
    "Acceptance",
    "Method",
)


def _snapshot_stub(
    logger: logging.Logger,
    epic: str = "",
    repo_dir: str = "",
) -> EpicSnapshot:
    return EpicSnapshot()


def _valid_stub(logger: logging.Logger, *args: object, **kwargs: object) -> Defects:
    return Defects(ok=True)


def _applied_stub(
    logger: logging.Logger,
    intent: EditIntent,
    snapshot: EpicSnapshot,
    plan: EpicEditPlan,
    repo_dir: str = "",
) -> AppliedEpicEdit:
    return AppliedEpicEdit(changed=True, deleted=True)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


@blueprint.node(stub=_snapshot_stub)
def snapshot_epic(
    logger: logging.Logger,
    epic: str = "",
    repo_dir: str = "",
) -> EpicSnapshot:
    """Capture the graph and story-body baseline an edit is allowed to change."""
    resolved_epics_dir = paths.epics_dir(repo_dir)
    okf = Ostler(repo_dir)
    frozen = (okf.graph.ids or {}).get("frozen") or {}
    wanted = registry.epic_slug(epic)
    epic_row = next(
        (row for row in okf.list("epic") if registry.epic_slug(str(row["name"])) == wanted),
        None,
    )
    if epic_row is None:
        raise WorkflowFailed(f"epic '{epic}' does not exist")
    name = str(epic_row["name"])
    epic_dir_rel = paths.epic_dir(repo_dir, name)
    seeds = [
        SeedSnapshot(
            id=str(row["id"]),
            status=str(row["status"]),
            summary=str(row["summary"]),
            surface=str(row["surface"]),
            legacy_surface=str(row["legacySurface"]),
            backing=str(row["backing"]),
            prerequisites=str(row["prerequisites"]),
            source_bullet=str(row["sourceBullet"]),
            frozen=str(row["id"]) in frozen,
        )
        for row in okf.list("seed", epic=name)
    ]
    stories = [
        StorySnapshot(
            slug=str(row["slug"]),
            title=str(row["title"]),
            status=str(row["status"]),
            covers=[str(value) for value in row["covers"]],
            depends=[str(value) for value in row["dependsOn"]],
            story_path=str(row["path"]),
            body_hash=_hash(Path(repo_dir) / str(row["path"])),
            frozen=str(row["slug"]) in frozen,
        )
        for row in okf.list("story", epic=name)
    ]
    milestones = [
        MilestoneSnapshot(
            name=str(row["name"]),
            source_items=[str(value) for value in row["sourceItems"]],
            epics=[str(value) for value in row["epics"]],
        )
        for row in okf.list("milestone")
        if any(registry.epic_slug(str(value)) == wanted for value in row["epics"])
    ]
    logger.info("snapshotted epic %s (%d seeds, %d stories)", name, len(seeds), len(stories))
    return EpicSnapshot(
        epic=name,
        epic_dir=epic_dir_rel,
        epics_dir=resolved_epics_dir,
        title=str(epic_row["title"]),
        epic_hash=_hash(Path(repo_dir) / epic_dir_rel / "epic.md"),
        seeds=seeds,
        stories=stories,
        milestones=milestones,
    )


def _project(plan: EpicEditPlan, snapshot: EpicSnapshot) -> tuple[dict[str, SeedSnapshot], dict[str, StorySnapshot]]:
    seeds = {seed.id: seed for seed in snapshot.seeds}
    stories = {story.slug: story for story in snapshot.stories}
    for change in plan.seed_changes:
        if change.action == "remove":
            seeds.pop(change.id, None)
        else:
            seeds[change.id] = SeedSnapshot(
                id=change.id,
                status=change.status,
                summary=change.summary,
                surface=change.surface,
                legacy_surface=change.legacy_surface,
                backing=change.backing,
                prerequisites=change.prerequisites,
                source_bullet=change.source_bullet,
            )
    for change in plan.story_changes:
        if change.action == "remove":
            stories.pop(change.slug, None)
        else:
            current = stories.get(change.slug, StorySnapshot(slug=change.slug))
            stories[change.slug] = current.model_copy(
                update={
                    "title": change.title,
                    "covers": list(change.covers),
                    "depends": list(change.depends),
                }
            )
    return seeds, stories


def _cycle(stories: dict[str, StorySnapshot]) -> str:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(slug: str) -> str:
        if slug in visiting:
            return slug
        if slug in visited:
            return ""
        visiting.add(slug)
        for dependency in stories[slug].depends:
            if dependency in stories and (hit := visit(dependency)):
                return hit
        visiting.remove(slug)
        visited.add(slug)
        return ""

    return next((hit for slug in stories if (hit := visit(slug))), "")


@blueprint.node(stub=_valid_stub)
def validate_edit_plan(
    logger: logging.Logger,
    intent: EditIntent,
    snapshot: EpicSnapshot,
    plan: EpicEditPlan,
    repo_dir: str = "",
) -> Defects:
    """Reject an unsafe projected graph before any Ostler mutation runs."""
    errors: list[str] = []
    if snapshot.epic_hash != _hash(Path(repo_dir) / snapshot.epic_dir / "epic.md"):
        errors.append("[E_PLANNER_MUTATION] planning turn changed epic.md before approval")
    for story in snapshot.stories:
        if story.body_hash != _hash(Path(repo_dir) / story.story_path):
            errors.append(
                f"[E_PLANNER_MUTATION] planning turn changed story '{story.slug}' before approval"
            )
    if plan.status != "complete":
        errors.append(f"[E_PLAN_BLOCKED] planner did not produce a complete plan: {plan.notes}")
    if registry.epic_slug(plan.epic) != registry.epic_slug(snapshot.epic):
        errors.append(f"[E_WRONG_EPIC] plan targets '{plan.epic}', expected '{snapshot.epic}'")

    for label, names in (
        ("seed", [change.id for change in plan.seed_changes]),
        ("story", [change.slug for change in plan.story_changes]),
    ):
        duplicates = sorted({name for name in names if name and names.count(name) > 1})
        if duplicates:
            errors.append(f"[E_DUPLICATE_OPERATION] {label}: {', '.join(duplicates)}")
        if any(not name for name in names):
            errors.append(f"[E_MISSING_ID] every {label} change needs an id")

    seeds, stories = _project(plan, snapshot)
    seed_ids = set(seeds)
    story_ids = set(stories)
    for story in stories.values():
        missing_covers = sorted(set(story.covers) - seed_ids)
        missing_dependencies = sorted(set(story.depends) - story_ids)
        if missing_covers:
            errors.append(
                f"[E_DANGLING_COVER] story '{story.slug}' covers missing seeds: "
                + ", ".join(missing_covers)
            )
        if missing_dependencies:
            errors.append(
                f"[E_DANGLING_DEPENDENCY] story '{story.slug}' is blocked by removed stories: "
                + ", ".join(missing_dependencies)
            )
    active = {seed.id for seed in seeds.values() if seed.status not in _INACTIVE_SEED_STATUSES}
    covered = {seed for story in stories.values() for seed in story.covers}
    if orphaned := sorted(active - covered):
        errors.append("[E_ORPHAN_SEED] active seeds have no resulting story: " + ", ".join(orphaned))
    if cycle := _cycle(stories):
        errors.append(f"[E_DEPENDENCY_CYCLE] resulting story graph cycles at '{cycle}'")

    if intent.kind == "add-story" and intent.bullet_id not in covered:
        errors.append(
            f"[E_ADD_NOT_SATISFIED] requested source item '{intent.bullet_id}' is not covered"
        )
    if intent.kind == "remove-story" and intent.story in stories:
        errors.append(f"[E_REMOVE_NOT_SATISFIED] requested story '{intent.story}' still exists")
    requested_story = next(
        (story for story in snapshot.stories if story.slug == intent.story),
        None,
    )
    implied_seed_removals = set(requested_story.covers if requested_story is not None else ())
    original_stories = {story.slug: story for story in snapshot.stories}
    original_seeds = {seed.id: seed for seed in snapshot.seeds}
    for change in plan.story_changes:
        if change.action != "remove" or change.slug not in original_stories:
            continue
        original = original_stories[change.slug]
        if original.frozen:
            errors.append(
                f"[E_FROZEN_SCOPE] story '{change.slug}' must be unfrozen before removal"
            )
        requested = intent.kind == "remove-story" and change.slug == intent.story
        if not intent.force and not requested:
            errors.append(
                f"[E_FORCE_REQUIRED] collateral story '{change.slug}' removal needs force=true"
            )
        elif not intent.force and original.status.lower() != "not started":
            errors.append(
                f"[E_FORCE_REQUIRED] story '{change.slug}' has status '{original.status}'"
            )
    for change in plan.seed_changes:
        if change.action != "remove" or change.id not in original_seeds:
            continue
        original = original_seeds[change.id]
        if original.frozen:
            errors.append(
                f"[E_FROZEN_SCOPE] seed '{change.id}' must be unfrozen before removal"
            )
        if not intent.force and change.id not in implied_seed_removals:
            errors.append(
                f"[E_FORCE_REQUIRED] collateral seed '{change.id}' removal needs force=true"
            )

    if plan.delete_epic != (not seeds and not stories):
        errors.append(
            "[E_EPIC_DELETION] delete_epic must be true exactly when no seeds and stories remain"
        )
    required_affected = {
        change.slug
        for change in plan.story_changes
        if change.action in {"add", "update"} and (change.action == "add" or change.rewrite)
    }
    if missing := sorted(required_affected - set(plan.affected_stories)):
        errors.append("[E_AFFECTED_STORY] changed stories omitted from rewrite: " + ", ".join(missing))

    logger.info("epic edit plan validation: %d error(s)", len(errors))
    return Defects(ok=not errors, errors="\n".join(errors))


def _seed_meta(change) -> dict[str, str]:
    return {
        "surface": change.surface,
        "legacySurface": change.legacy_surface,
        "backing": change.backing,
        "prerequisites": change.prerequisites,
        "sourceBullet": change.source_bullet,
    }


def _source_id(text: str) -> str:
    bullets = markdown.split(f"- {text}\n").walk_bullets()
    return bullets[0].bracketed[0] if bullets else ""


@blueprint.node(stub=_applied_stub)
def apply_edit_plan(
    logger: logging.Logger,
    intent: EditIntent,
    snapshot: EpicSnapshot,
    plan: EpicEditPlan,
    repo_dir: str = "",
) -> AppliedEpicEdit:
    """Apply one validated plan idempotently through Ostler's structural APIs."""
    okf = Ostler(repo_dir)
    epic = snapshot.epic
    for change in plan.story_changes:
        if change.action == "remove" and any(
            str(row["slug"]) == change.slug for row in okf.list("story", epic=epic)
        ):
            result = okf.delete_story(change.slug)
            if not result.ok:
                raise WorkflowFailed(result.message)
    for change in plan.seed_changes:
        existing = {str(row["id"]) for row in okf.list("seed", epic=epic)}
        if change.action == "remove":
            if change.id in existing:
                result = okf.remove_seed(epic, change.id)
                if not result.ok:
                    raise WorkflowFailed(result.message)
            continue
        result = okf.add_seed(
            epic,
            change.id,
            status=change.status,
            summary=change.summary,
            meta=_seed_meta(change),
        )
        if not result.ok:
            raise WorkflowFailed(result.message)
    for change in plan.story_changes:
        if change.action == "remove":
            continue
        existing = {str(row["slug"]) for row in okf.list("story", epic=epic)}
        if change.slug in existing:
            result = okf.update_story(
                change.slug,
                title=change.title,
                covers=change.covers,
                depends=change.depends,
            )
        else:
            result = okf.create_story(
                epic,
                change.slug,
                change.title,
                covers=change.covers,
                depends=change.depends,
            )
        if not result.ok:
            raise WorkflowFailed(result.message)

    removed_source_ids = {
        source_id
        for change in plan.seed_changes
        if change.action == "remove" and change.disposition == "drop"
        if (source_id := _source_id(
            next((seed.source_bullet for seed in snapshot.seeds if seed.id == change.id), "")
        ))
    }
    for milestone in snapshot.milestones:
        source_items = [item for item in milestone.source_items if item not in removed_source_ids]
        if intent.kind == "add-story" and intent.bullet_id and intent.bullet_id not in source_items:
            source_items.append(intent.bullet_id)
        if source_items != milestone.source_items:
            result = okf.set_milestone_source_items(milestone.name, source_items)
            if not result.ok:
                raise WorkflowFailed(result.message)

    if plan.delete_epic:
        result = okf.delete_epic(epic)
        if not result.ok:
            raise WorkflowFailed(result.message)
        logger.info("deleted empty epic %s", epic)
        return AppliedEpicEdit(
            changed=True,
            epic=epic,
            epic_dir=snapshot.epic_dir,
            deleted=True,
            removed_stories=[
                change.slug for change in plan.story_changes if change.action == "remove"
            ],
        )

    affected = list(dict.fromkeys([
        *plan.affected_stories,
        *(change.slug for change in plan.story_changes if change.action == "add"),
    ]))
    logger.info("applied epic edit to %s (%d affected stories)", epic, len(affected))
    return AppliedEpicEdit(
        changed=True,
        epic=epic,
        epic_dir=snapshot.epic_dir,
        affected_stories=affected,
        removed_stories=[
            change.slug for change in plan.story_changes if change.action == "remove"
        ],
    )


@blueprint.node(stub=_valid_stub)
def validate_applied_edit(
    logger: logging.Logger,
    snapshot: EpicSnapshot,
    plan: EpicEditPlan,
    applied: AppliedEpicEdit,
    repo_dir: str = "",
) -> Defects:
    """Prove disk matches the approved graph and unaffected story bodies remain byte-stable."""
    okf = Ostler(repo_dir)
    if applied.deleted:
        exists = any(
            registry.epic_slug(str(row["name"])) == registry.epic_slug(snapshot.epic)
            for row in okf.list("epic")
        )
        return Defects(
            ok=not exists,
            errors="[E_APPLY_DELTA] deleted epic still exists" if exists else "",
        )
    affected = {*applied.affected_stories, *applied.removed_stories}
    errors: list[str] = []
    expected_seeds, expected_stories = _project(plan, snapshot)
    actual_seeds = {
        str(row["id"]): row for row in okf.list("seed", epic=snapshot.epic)
    }
    actual_stories = {
        str(row["slug"]): row for row in okf.list("story", epic=snapshot.epic)
    }
    if set(actual_seeds) != set(expected_seeds):
        errors.append(
            "[E_APPLY_DELTA] resulting seeds differ from the approved plan: "
            f"expected {sorted(expected_seeds)}, got {sorted(actual_seeds)}"
        )
    if set(actual_stories) != set(expected_stories):
        errors.append(
            "[E_APPLY_DELTA] resulting stories differ from the approved plan: "
            f"expected {sorted(expected_stories)}, got {sorted(actual_stories)}"
        )
    for seed_id, expected in expected_seeds.items():
        actual = actual_seeds.get(seed_id)
        if actual is None:
            continue
        actual_state = (
            str(actual["status"]),
            str(actual["summary"]),
            str(actual["surface"]),
            str(actual["legacySurface"]),
            str(actual["backing"]),
            str(actual["prerequisites"]),
            str(actual["sourceBullet"]),
        )
        expected_state = (
            expected.status,
            expected.summary,
            expected.surface,
            expected.legacy_surface,
            expected.backing,
            expected.prerequisites,
            expected.source_bullet,
        )
        if actual_state != expected_state:
            errors.append(f"[E_APPLY_DELTA] seed '{seed_id}' metadata differs from the plan")
    for slug, expected in expected_stories.items():
        actual = actual_stories.get(slug)
        if actual is None:
            continue
        actual_state = (
            str(actual["title"]),
            [str(value) for value in actual["covers"]],
            [str(value) for value in actual["dependsOn"]],
        )
        expected_state = (expected.title, expected.covers, expected.depends)
        if actual_state != expected_state:
            errors.append(f"[E_APPLY_DELTA] story '{slug}' metadata differs from the plan")
    for story in snapshot.stories:
        if story.slug in affected or not story.story_path:
            continue
        current = _hash(Path(repo_dir) / story.story_path)
        if current != story.body_hash:
            errors.append(
                f"[E_UNDECLARED_CHANGE] unaffected story '{story.slug}' body changed"
            )
    logger.info("applied epic edit validation: %d error(s)", len(errors))
    return Defects(ok=not errors, errors="\n".join(errors))


@blueprint.node(stub=_valid_stub)
def validate_epic_document(
    logger: logging.Logger,
    epic_dir: str = "",
    repo_dir: str = "",
) -> Defects:
    """Check the model-authored epic prose without re-parsing Ostler-owned graph metadata."""
    epic_path = Path(repo_dir) / epic_dir / "epic.md"
    if not epic_path.is_file():
        return Defects(errors=f"[E_EPIC_DOCUMENT] no epic document at {epic_path}")
    doc = markdown.split(epic_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    for heading in _REQUIRED_EPIC_SECTIONS:
        section = doc.find_section(heading)
        if section is None:
            errors.append(f"[E_EPIC_SECTION] missing ## {heading}")
        elif section.is_empty:
            errors.append(f"[E_EPIC_SECTION] empty ## {heading}")
    journeys = doc.find_section("User Journeys")
    if journeys is not None and not journeys.children:
        errors.append("[E_EPIC_JOURNEY] ## User Journeys needs at least one ### journey")
    logger.info("epic document validation: %d error(s)", len(errors))
    return Defects(ok=not errors, errors="\n".join(errors))


@blueprint.node
def select_affected_story(
    logger: logging.Logger,
    epic: str,
    affected_stories: list[str],
    index: int,
    repo_dir: str = "",
) -> StoryChoice:
    """Resolve the next approved affected story without widening the edit worklist."""
    if index >= len(affected_stories):
        return StoryChoice(reason="every affected story is authored")
    slug = affected_stories[index]
    row = next(
        (
            row
            for row in Ostler(repo_dir).list("story", epic=epic)
            if str(row["slug"]) == slug
        ),
        None,
    )
    if row is None:
        raise WorkflowFailed(f"affected story '{slug}' does not exist after applying the plan")
    path = str(row["path"])
    logger.info("selected affected story '%s' (%d/%d)", slug, index + 1, len(affected_stories))
    return StoryChoice(
        has_story=True,
        story_path=path,
        story_slug=slug,
        story_dir=str(Path(path).parent),
        progress=f"{index + 1}/{len(affected_stories)}",
        remaining_count=len(affected_stories) - index - 1,
    )


__all__ = [
    "apply_edit_plan",
    "blueprint",
    "select_affected_story",
    "snapshot_epic",
    "validate_applied_edit",
    "validate_edit_plan",
    "validate_epic_document",
]
