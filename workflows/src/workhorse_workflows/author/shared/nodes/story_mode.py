"""Story mode's backlog edits: adopt the backlog's ids, resolve a bullet, seed its story, prune it."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from ostler import Ostler, backlog as ostler_backlog, markdown
from ostler.result import Result
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.author.shared.nodes.blueprint import blueprint
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.paths import survey_repo_root
from workhorse_workflows.author.shared.schemas.edit import ResolvedBullet
from workhorse_workflows.author.shared.schemas.main import Pruned, SeededStory


@blueprint.node
def adopt_backlog(
    logger: logging.Logger,
    repo_dir: str = "",
) -> Result:
    """Mint ids for every unnamed backlog bullet before decomposition or story lookup."""
    result = Ostler(survey_repo_root(repo_dir)).backlog_adopt()
    if not result.ok:
        raise WorkflowFailed(result.message)
    logger.info(result.message)
    return result


def _kebab(text: str, *, max_len: int = 60) -> str:
    """Lowercase kebab id from free text: alnum runs joined by single dashes."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip("-")
    return slug or "story"


def resolve_bullet(root: Path, bullet: str) -> ResolvedBullet:
    """Resolve one requested bullet against the repo's backlog."""
    backlog_path = root / paths.backlog_file(root)
    raw = bullet.strip()
    bare = raw[1:-1].strip() if raw.startswith("[") and raw.endswith("]") else raw

    if backlog_path.is_file():
        try:
            text = backlog_path.read_text(encoding="utf-8")
        except OSError:
            text = ""
        for item in markdown.split(text).walk_bullets():
            bid, btext = item.bracketed
            if bid and (
                bare == bid
                or raw.lstrip("-").strip() == item.text.strip()
                or (btext and btext == raw)
            ):
                return ResolvedBullet(id=bid, source_bullet=item.text.strip(), from_backlog=True)

    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", bare):
        return ResolvedBullet(id=bare, source_bullet=bare)
    return ResolvedBullet(id=_kebab(raw), source_bullet=raw)


@blueprint.node
def seed_story(
    logger: logging.Logger,
    epic: str = "",
    bullet: str = "",
    layers: str = "",
    services: str = "",
    repo_dir: str = "",
) -> SeededStory:
    """Register ONE bullet as a new story inside an already-existing epic."""
    epic = epic.strip()
    bullet = bullet.strip()

    if not epic:
        raise WorkflowFailed(
            "no epic supplied — story mode needs the target epic slug "
            "(--params '{\"mode\":\"story\",\"epic\":\"<slug>\",\"bullet\":\"...\"}')"
        )
    if not bullet:
        raise WorkflowFailed(
            "no bullet supplied — story mode needs a backlog [id] or literal bullet text "
            "(--params '{\"mode\":\"story\",\"epic\":\"<slug>\",\"bullet\":\"...\"}')"
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

    resolved = resolve_bullet(root, bullet)
    bullet_id = resolved.id
    source_bullet = resolved.source_bullet
    from_backlog = resolved.from_backlog

    for s in okf.list("story", epic=epic):
        if bullet_id in (s.get("covers") or []):
            slug = str(s.get("slug", ""))
            path = str(s.get("path", "")) or f"{paths.story_dir(epic_dir_rel, slug)}/story.md"
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            reason = f"story '{slug}' already covers '{bullet_id}' — reusing (idempotent)"
            logger.info("story '%s' already covers '%s' — reusing (idempotent)", slug, bullet_id)
            return SeededStory(
                epic_dir=epic_dir_rel,
                story_slug=slug,
                story_dir=str(Path(path).parent),
                story_path=path,
                bullet_id=bullet_id,
                from_backlog=from_backlog,
                reason=reason,
            )

    seed_meta: dict[str, str] = {"sourceBullet": source_bullet}
    if layers.strip():
        seed_meta["layers"] = layers.strip()
    if services.strip():
        seed_meta["services"] = services.strip()
    seeded = okf.add_seed(epic, bullet_id, status="researched", summary=source_bullet,
                          meta=seed_meta)
    if not seeded.ok and layers.strip():
        raise WorkflowFailed(f"`seed add {epic} {bullet_id}` failed: {seeded.message}")

    slug = _kebab(source_bullet)
    res = okf.create_story(epic, slug, source_bullet, covers=[bullet_id])
    if not res.ok:
        raise WorkflowFailed(f"`create story {epic} {slug}` failed: {res.message}")

    story_dir_rel = paths.story_dir(epic_dir_rel, slug)
    reason = (
        f"registered story '{slug}' ({res.entity_id or '?'}) covering seed item "
        f"'{bullet_id}' in epic '{epic}'"
    )
    logger.info(
        "registered story '%s' (%s) covering seed item '%s' in epic '%s'",
        slug,
        res.entity_id or "?",
        bullet_id,
        epic,
    )
    return SeededStory(
        epic_dir=epic_dir_rel,
        story_slug=slug,
        story_dir=story_dir_rel,
        story_path=f"{story_dir_rel}/story.md",
        bullet_id=bullet_id,
        from_backlog=from_backlog,
        reason=reason,
    )


@blueprint.node
def prune_bullet(
    logger: logging.Logger,
    bullet_id: str = "",
    from_backlog: bool = False,
    repo_dir: str = "",
) -> Pruned:
    """Remove the one backlog bullet story mode consumed — story mode's tail."""
    bullet_id = bullet_id.strip()

    if not from_backlog or not bullet_id:
        logger.info("bullet '%s' is not from the backlog (or missing) — no-op", bullet_id)
        return Pruned()

    root = survey_repo_root(repo_dir)
    backlog_rel = paths.backlog_file(root)
    backlog_path = root / backlog_rel
    if not backlog_path.is_file():
        logger.info("no backlog at %s — nothing to prune", backlog_path)
        return Pruned()

    try:
        raw = backlog_path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("could not read backlog %s — nothing to prune", backlog_path)
        return Pruned()

    doc = markdown.split(raw)
    offset = doc.body_offset
    bullets = doc.walk_bullets()
    targets = [item for item in bullets if item.bracketed[0] == bullet_id]
    body_drop = ostler_backlog.removal_lines(targets)
    drop = {line + offset for line in body_drop}
    removed = sum(1 for item in targets if item.line_start in body_drop)
    remaining = sum(
        1 for item in bullets if item.bracketed[0] and item.line_start + offset not in drop
    )

    lines = raw.splitlines(keepends=True)
    kept = [line for i, line in enumerate(lines) if i not in drop]

    if removed:
        try:
            backlog_path.write_text("".join(kept), encoding="utf-8")
        except OSError:
            logger.warning(
                "could not write pruned backlog %s — best-effort, continuing", backlog_path
            )

    logger.info(
        "pruned bullet '%s' from %s (removed=%d, remaining=%d)",
        bullet_id,
        backlog_rel,
        removed,
        remaining,
    )
    return Pruned(removed=removed, remaining=remaining)


__all__ = ["adopt_backlog", "prune_bullet", "resolve_bullet", "seed_story"]
