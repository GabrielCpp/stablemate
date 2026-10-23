"""Story mode's register edits: resolve a record, seed its story, close it as promoted."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from ostler import Ostler, register
from ostler.register import Record
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.author.shared.nodes.blueprint import blueprint
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.paths import survey_repo_root
from workhorse_workflows.author.shared.schemas.main import Promoted, SeededStory


def _kebab(text: str, *, max_len: int = 60) -> str:
    """Lowercase kebab id from free text: alnum runs joined by single dashes."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip("-")
    return slug or "story"


def find_record(root: Path, token: str) -> Record:
    """The record a token names, whatever its status; a token naming none fails the run."""
    token = token.strip()
    folder = register.locate(Ostler(root).graph, token)
    if folder is None:
        raise WorkflowFailed(f"no record '{token}' on the register — file it with `ostler backlog add`, then pick it")
    return Record.read(folder / register.RECORD_FILE)


def resolve_record(root: Path, token: str) -> Record:
    """The open record a token names; a token naming none, or a closed record, fails the run."""
    record = find_record(root, token)
    if record.status != "open":
        raise WorkflowFailed(f"record '{token}' is {record.status}, not open — only an open record can be picked")
    return record


def seed_text(record: Record) -> str:
    """The text a story is seeded from: the record's summary, then its body."""
    return f"{record.summary}\n\n{record.body}" if record.body else record.summary


@blueprint.node
def seed_story(
    logger: logging.Logger,
    epic: str = "",
    record: str = "",
    layers: str = "",
    services: str = "",
    repo_dir: str = "",
) -> SeededStory:
    """Register ONE register record as a new story inside an already-existing epic."""
    epic = epic.strip()
    record = record.strip()

    if not epic:
        raise WorkflowFailed(
            "no epic supplied — story mode needs the target epic slug "
            "(--params '{\"mode\":\"story\",\"epic\":\"<slug>\",\"record\":\"<record id>\"}')"
        )
    if not record:
        raise WorkflowFailed(
            "no record supplied — story mode needs the id of an open register record "
            "(--params '{\"mode\":\"story\",\"epic\":\"<slug>\",\"record\":\"<record id>\"}')"
        )

    root = survey_repo_root(repo_dir)
    okf = Ostler(root)
    epic_dir_rel = paths.epic_dir(root, epic)
    epic_dir_abs = root / epic_dir_rel

    if not (epic_dir_abs / "epic.md").is_file():
        raise WorkflowFailed(
            f"epic '{epic}' does not exist at {epic_dir_abs}/epic.md — story mode appends to an "
            "EXISTING epic and never creates one; run epic mode first or fix the epic slug"
        )

    found = find_record(root, record)
    record_id = found.id

    for s in okf.list("story", epic=epic):
        if record_id in (s.get("covers") or []):
            slug = str(s.get("slug", ""))
            path = str(s.get("path", "")) or f"{paths.story_dir(epic_dir_rel, slug)}/story.md"
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            reason = f"story '{slug}' already covers '{record_id}' — reusing (idempotent)"
            logger.info("story '%s' already covers '%s' — reusing (idempotent)", slug, record_id)
            return SeededStory(
                epic_dir=epic_dir_rel,
                story_slug=slug,
                story_dir=str(Path(path).parent),
                story_path=path,
                record_id=record_id,
                reason=reason,
            )

    found = resolve_record(root, record)
    seed_meta: dict[str, str] = {"sourceRecord": record_id}
    if layers.strip():
        seed_meta["layers"] = layers.strip()
    if services.strip():
        seed_meta["services"] = services.strip()
    seeded = okf.add_seed(epic, record_id, status="researched", summary=seed_text(found),
                          meta=seed_meta)
    if not seeded.ok and layers.strip():
        raise WorkflowFailed(f"`seed add {epic} {record_id}` failed: {seeded.message}")

    slug = _kebab(found.summary)
    res = okf.create_story(epic, slug, found.summary, covers=[record_id])
    if not res.ok:
        raise WorkflowFailed(f"`create story {epic} {slug}` failed: {res.message}")

    story_dir_rel = paths.story_dir(epic_dir_rel, slug)
    reason = (
        f"registered story '{slug}' ({res.entity_id or '?'}) covering seed item "
        f"'{record_id}' in epic '{epic}'"
    )
    logger.info(
        "registered story '%s' (%s) covering seed item '%s' in epic '%s'",
        slug,
        res.entity_id or "?",
        record_id,
        epic,
    )
    return SeededStory(
        epic_dir=epic_dir_rel,
        story_slug=slug,
        story_dir=story_dir_rel,
        story_path=f"{story_dir_rel}/story.md",
        record_id=record_id,
        reason=reason,
    )


@blueprint.node
def promote_record(
    logger: logging.Logger,
    record_id: str = "",
    epic: str = "",
    story: str = "",
    repo_dir: str = "",
) -> Promoted:
    """Close the record a story was authored from as promoted, naming the story and its epic."""
    record_id = record_id.strip()
    if not record_id:
        raise WorkflowFailed("no record id supplied — nothing to close as promoted")
    okf = Ostler(survey_repo_root(repo_dir))
    slug = story.strip()
    if not slug:
        slug = next(
            (
                str(row.get("slug", ""))
                for row in okf.list("story", epic=epic)
                if record_id in (row.get("covers") or [])
            ),
            "",
        )
    if not slug:
        raise WorkflowFailed(f"no story of epic '{epic}' covers record '{record_id}'")
    reason = f"promoted to story {slug} in epic {epic}"
    result = okf.close_record(record_id, "promoted", reason)
    if not result.ok:
        raise WorkflowFailed(f"record '{record_id}' was not closed as promoted: {result.message}")
    logger.info("closed '%s' as promoted: %s", record_id, reason)
    return Promoted(record_id=record_id, reason=reason)


__all__ = ["find_record", "promote_record", "resolve_record", "seed_story", "seed_text"]
