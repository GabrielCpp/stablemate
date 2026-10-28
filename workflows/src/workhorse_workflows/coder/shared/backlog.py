"""The backlog, both ends of it: what the coder files into it, and what it drains back out."""
from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ostler import Ostler, ids, markdown
from ostler.register import Record
from ostler.path import book_prefix_in
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.kit import find_docs_root
from workhorse_workflows.kit.workspace import resolve_workspace
from workhorse_workflows.coder.shared import causes, paths
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.docs import CONTEXT_FILE
from workhorse_workflows.coder.shared.judge import Judge
from workhorse_workflows.coder.shared.schemas.backlog import (
    FiledBacklog,
    FixClosed,
    FixPick,
    FixStorySeed,
)
from workhorse_workflows.coder.shared.schemas.dev_story import FollowUp
from workhorse_workflows.coder.shared.schemas.qa import BacklogDrain

@dataclass(frozen=True)
class BacklogBullet:
    """One `[id] text` open item, as the follow-up filer compares a new one against it."""

    line: int
    id: str
    text: str


def kebab(raw: str) -> str:
    """Sanitize an id to a stable kebab handle."""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", str(raw).strip().lower()).strip("-")


def norm_desc(desc: str) -> str:
    """Normalize a description to an identity key; empty means "never matches"."""
    return re.sub(r"[^a-z0-9]+", " ", str(desc or "").lower()).strip()


def id_token_set(item_id: str) -> frozenset[str]:
    """The tokens of a kebab id, order-insensitive, so a word-permuted re-file collides."""
    return frozenset(t for t in re.split(r"[.\-_]+", str(item_id or "").lower()) if t)


def _load_items(logger: logging.Logger, items_path: Path) -> list[dict[str, Any]]:
    """The filed items, or `[]` — an unreadable or malformed file is a logged no-op."""
    if not items_path.is_file():
        return []
    try:
        data = json.loads(items_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("items file unreadable: %s", exc)
        return []
    if isinstance(data, dict):
        data = data.get("items") or []
    return [item for item in data if isinstance(item, dict)]


def _item_entry(item: dict[str, Any]) -> tuple[str, str]:
    """An item's kebab id and its one-line description."""
    return kebab(item.get("id") or ""), str(item.get("description") or "").strip().replace("\n", " ")


def _segment(raw: object) -> str:
    """A register repo, area or pattern segment from free text: lowercase kebab, or `untriaged` when nothing is left."""
    return re.sub(r"[^a-z0-9]+", "-", str(raw or "").lower()).strip("-") or "untriaged"


def _items_file(root: Path, spec_dir: str) -> Path | None:
    spec = spec_dir.strip()
    return root / spec / "backlog-items.json" if spec else None


@blueprint.node
def filed_backlog(
    logger: logging.Logger, spec_dir: str = "", repo_dir: str = "", workspace: str = ""
) -> FiledBacklog:
    """The open `qa` records of the workspace's repos, and the items the story's QA left to file, so a flow can judge them first."""
    root = find_docs_root(repo_dir)
    repos = resolve_workspace(workspace, repo_dir)
    filed = {
        r.id: r.summary
        for r in Ostler(root).records().records
        if r.repo in repos and r.status == "open" and r.filed_by == "qa"
    }
    items_path = _items_file(root, spec_dir)
    pending = _load_items(logger, items_path) if items_path else []
    items = {item_id: desc for item_id, desc in map(_item_entry, pending) if item_id and desc}
    return FiledBacklog(filed=filed, items=items)


def unfiled(
    judge: Judge, logger: logging.Logger, reports: Mapping[str, str], filed: Mapping[str, str]
) -> list[str]:
    """The reports that restate no open `qa` record; each one that does is logged under the record it matched."""
    same = causes.same_causes(judge, reports, filed)
    for rid, hit in same.items():
        if hit != causes.NEW:
            logger.info("[%s] already holds %r, so it is not filed again", hit, reports[rid])
    return [rid for rid, hit in same.items() if hit == causes.NEW]


def _story_of(root: Path, spec_dir: str) -> str:
    """The story id the spec dir's QA context names, or empty when it names none."""
    context_path = root / spec_dir.strip() / CONTEXT_FILE
    try:
        return _story_id(json.loads(context_path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return ""


@blueprint.node
def file_backlog_items(
    logger: logging.Logger,
    spec_dir: str = "",
    repo_dir: str = "",
    workspace: str = "",
    drop: list[str] | None = None,
) -> BacklogDrain:
    """File this story's leftover items as `qa` records on the register, less the ones in `drop`, de-duplicated,, then clear them."""
    root = find_docs_root(repo_dir)
    items_path = _items_file(root, spec_dir)
    if items_path is None:
        logger.info("no spec_dir supplied — nothing to drain")
        return BacklogDrain(notes="no spec_dir supplied — nothing to drain")

    items = _load_items(logger, items_path)
    if not items:
        logger.info("no backlog items to file at %s", items_path)
        return BacklogDrain(notes="no backlog items to file")

    okf = Ostler(root)
    repos = resolve_workspace(workspace, repo_dir)
    story = _story_of(root, spec_dir)
    held: dict[str, set[str]] = {}
    new_paths: list[Path] = []
    dropped = set(drop or [])
    skipped = 0
    for item in items:
        item_id, desc = _item_entry(item)
        if not item_id or not desc or item_id in dropped:
            skipped += 1
            continue
        repo = _workspace_repo(str(item.get("repo") or "").strip(), repos)
        if not repo:
            logger.info(
                "item %r names no repository of the workspace (%s), so it is not filed",
                desc, ", ".join(repos),
            )
            skipped += 1
            continue
        if repo not in held:
            held[repo] = {
                norm_desc(r.summary) for r in okf.open_records(repo) if r.filed_by == "qa"
            }
        key = norm_desc(desc)
        if key in held[repo]:
            logger.info("item %r restates an open qa record of %s, so it is not filed again", desc, repo)
            skipped += 1
            continue
        full = str(item.get("description") or "").strip()
        filing = okf.file_record(
            repo=repo,
            area=_segment(item.get("area")),
            pattern=_segment(item.get("pattern")),
            summary=next((line.strip() for line in full.splitlines() if line.strip()), desc),
            filed_by="qa",
            symbols=[str(s) for s in item.get("symbols") or [] if isinstance(s, str)],
            source_story=story,
            body=full if "\n" in full else "",
        )
        if filing.record is None or filing.path is None:
            logger.info("item %r was not filed: %s", desc, filing.message)
            skipped += 1
            continue
        held[repo].add(key)
        new_paths.append(filing.path)

    appended = len(new_paths)

    try:
        items_path.unlink()
        removed = True
    except OSError as exc:
        logger.warning("could not remove items file: %s", exc)
        removed = False

    note = f"filed {appended} to the register, skipped {skipped} (duplicate/invalid)"
    note += "; removed backlog-items.json" if removed else "; backlog-items.json left in place"
    logger.info(note)
    return BacklogDrain(appended=appended, skipped=skipped, notes=note)


def _filed_as(bullets: list[BacklogBullet], title: str, reason: str) -> str:
    """The id of the backlog item a follow-up already is: cited, one word off its id, or the same title."""
    cited = f"{title} {reason}"
    words = id_token_set(kebab(title))
    heading = norm_desc(title)
    for bullet in bullets:
        if f"[{bullet.id}]" in cited:
            return bullet.id
        tokens = id_token_set(bullet.id)
        if min(len(tokens), len(words)) >= 3 and len(tokens ^ words) <= 1:
            return bullet.id
        if heading and norm_desc(bullet.text.split(": ", 1)[0]) == heading:
            return bullet.id
    return ""


def _workspace_repo(named: str, repos: Mapping[str, Any]) -> str:
    """The workspace repository a filing belongs to: the one it names, else the only one, else empty."""
    if named in repos:
        return named
    return next(iter(repos)) if len(repos) == 1 else ""


@blueprint.node
def file_follow_up_backlog(
    logger: logging.Logger,
    parent: str = "",
    follow_ups: list[FollowUp] | None = None,
    repo_dir: str = "",
    workspace: str = "",
) -> BacklogDrain:
    """File a dev turn's follow-ups as records on the debt register."""
    okf = Ostler(find_docs_root(repo_dir))
    repos = resolve_workspace(workspace, repo_dir)
    open_by_repo: dict[str, list[BacklogBullet]] = {}
    new_paths: list[Path] = []
    skipped = 0
    for entry in follow_ups or []:
        title = " ".join(entry.title.split())
        reason = entry.reason.strip()
        if not title:
            skipped += 1
            continue
        repo = _workspace_repo(entry.repo.strip(), repos)
        if not repo:
            logger.info(
                "follow-up %r names no repository of the workspace (%s), so it is not filed",
                title, ", ".join(repos),
            )
            skipped += 1
            continue
        missing = [name for name in ("area", "pattern") if not getattr(entry, name).strip()]
        if missing:
            logger.info("follow-up %r has no %s, so it is not filed", title, " and no ".join(missing))
            skipped += 1
            continue
        if repo not in open_by_repo:
            open_by_repo[repo] = [
                BacklogBullet(0, record.id, record.summary) for record in okf.open_records(repo)
            ]
        filed = _filed_as(open_by_repo[repo], title, reason)
        if filed:
            logger.info("follow-up %r is already on the register as [%s]", title, filed)
            skipped += 1
            continue
        filing = okf.file_record(
            repo=repo, area=entry.area.strip(), pattern=entry.pattern.strip(), summary=title,
            filed_by="coder", symbols=entry.symbols, source_story=parent, body=reason,
        )
        if filing.record is None or filing.path is None:
            logger.info("follow-up %r was not filed: %s", title, filing.message)
            skipped += 1
            continue
        open_by_repo[repo].append(BacklogBullet(0, filing.record.id, filing.record.summary))
        new_paths.append(filing.path)
    appended = len(new_paths)
    note = f"filed {appended} follow-up(s) of {parent} to the register, skipped {skipped}"
    logger.info(note)
    return BacklogDrain(appended=appended, skipped=skipped, notes=note)


def _deferred_pages(context: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """The required obligations ostler deferred, grouped by the book page that owes their check."""
    pages: dict[str, list[dict[str, Any]]] = {}
    for obligation in context.get("obligations") or []:
        if not isinstance(obligation, dict) or obligation.get("required", True) is False:
            continue
        if not isinstance(obligation.get("deferred"), dict):
            continue
        node = str(obligation.get("node") or "")
        page = str(obligation.get("source") or node.partition("#")[0])
        if page:
            pages.setdefault(page, []).append(obligation)
    return pages


def _deferred_text(page: str, obligations: list[dict[str, Any]]) -> str:
    """One backlog line for a page: the claims QA skipped, and what the book has to add."""
    anchors: list[str] = []
    details: list[str] = []
    for obligation in obligations:
        node = str(obligation.get("node") or page)
        anchor = node.partition("#")[2]
        anchors.append(f"`#{anchor}`" if anchor else "the page itself")
        detail = str(obligation["deferred"].get("detail") or "").replace(f"`{node}`", "a section")
        detail = " ".join(detail.split())
        if detail:
            details.append(detail[0].upper() + detail[1:] + ("" if detail.endswith(".") else "."))
    claims = ", ".join(dict.fromkeys(anchors))
    head = (
        f"Book page `{page}` gives QA no check it can run for {claims}, "
        "so a story that changes its code ships them unproved."
    )
    return " ".join([head, *dict.fromkeys(details)])


def _feature_path(page: str, services: str, root: Path) -> Path:
    """A book page's path under the services root, which the context may give as an absolute path."""
    base = Path(services)
    if base.is_absolute():
        base = Path(os.path.relpath(base, root))
    path = Path(page)
    return path.relative_to(base) if services and path.is_relative_to(base) else path


def _book_repo(page: str, services: str, root: Path) -> str:
    """The repository name a book page points at: its book's prefix under *root*, else its own first path segment."""
    base = Path(services)
    relative = Path(os.path.relpath(base, root)) if base.is_absolute() else base
    prefix = book_prefix_in(root, relative.as_posix()) if services else ""
    path = Path(page)
    placed = Path(os.path.relpath(path, root)) if path.is_absolute() else path
    return (Path(prefix).parts or placed.parts or ("",))[0]


def _story_id(context: object) -> str:
    """The id of the story the QA context packet names, or empty when it names none."""
    story = context.get("story") if isinstance(context, dict) else None
    return str(story.get("id") or "") if isinstance(story, dict) else ""


@blueprint.node
def file_deferred_obligations(
    logger: logging.Logger, spec_dir: str = "", repo_dir: str = "", workspace: str = ""
) -> BacklogDrain:
    """File each book page that owes QA a check it could not run as a record on the register."""
    root = find_docs_root(repo_dir)
    spec = spec_dir.strip()
    context_path = root / spec / CONTEXT_FILE
    if not spec or not context_path.is_file():
        return BacklogDrain(notes="no QA context to read deferred obligations from")
    try:
        context = json.loads(context_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("QA context unreadable: %s", exc)
        return BacklogDrain(notes=f"QA context unreadable: {exc}")
    pages = _deferred_pages(context) if isinstance(context, dict) else {}
    services = str(context.get("servicesRoot") or "") if isinstance(context, dict) else ""
    source_story = _story_id(context)
    okf = Ostler(root)
    repos = resolve_workspace(workspace, repo_dir)
    open_by_repo: dict[str, list[Any]] = {}
    new_paths: list[Path] = []
    skipped = 0
    for page, obligations in pages.items():
        rel = _feature_path(page, services, root).as_posix()
        repo = _workspace_repo(_book_repo(page, services, root), repos)
        if not repo:
            logger.info(
                "book page %r belongs to no repository of the workspace (%s), so it is not filed",
                page, ", ".join(repos),
            )
            skipped += 1
            continue
        if repo not in open_by_repo:
            open_by_repo[repo] = okf.open_records(repo)
        if any(r.filed_by == "qa-deferred" and rel in r.symbols for r in open_by_repo[repo]):
            logger.info("book page %r already has an open record, so it is not filed again", page)
            skipped += 1
            continue
        filing = okf.file_record(
            repo=repo, area="book", pattern="add-runnable-check",
            summary=f"Book page `{page}` gives QA no check it can run", filed_by="qa-deferred",
            symbols=[rel], source_story=source_story, body=_deferred_text(page, obligations),
        )
        if filing.record is None or filing.path is None:
            logger.info("book page %r was not filed: %s", page, filing.message)
            skipped += 1
            continue
        open_by_repo[repo].append(filing.record)
        new_paths.append(filing.path)
    appended = len(new_paths)
    note = f"filed {appended} book page(s) with deferred checks to the register, skipped {skipped}"
    logger.info(note)
    return BacklogDrain(appended=appended, skipped=skipped, notes=note)


def _age(record: Record) -> tuple[bool, str, str]:
    """Oldest first: an id that carries no ULID (an imported one) before every minted id, minted ids by their ULID."""
    ulid = ids.ulid_of(record.id)
    return bool(ulid), ulid, record.id


@blueprint.node
def select_fix_item(
    logger: logging.Logger, repo_dir: str = "", workspace: str = ""
) -> FixPick:
    """Draw the oldest open `qa` record of the workspace's repos, or report the pool dry."""
    root = find_docs_root(repo_dir)
    repos = resolve_workspace(workspace, repo_dir)
    drainable = sorted(
        (
            r
            for r in Ostler(root).records().records
            if r.repo in repos and r.status == "open" and r.filed_by == "qa"
        ),
        key=_age,
    )
    if not drainable:
        logger.info("no open qa record in %s — nothing to drain", ", ".join(repos))
        return FixPick(reason=f"no open qa record in {', '.join(repos)} — nothing to drain")
    record = drainable[0]
    logger.info("drew '%s' from the register", record.id)
    return FixPick(
        has_fix=True,
        record_id=record.id,
        repo=record.repo,
        area=record.area,
        summary=record.summary,
        body=record.body,
        reason=f"drew '{record.id}' from the register",
    )


@blueprint.node
def seed_fix_story(
    logger: logging.Logger,
    record_id: str = "",
    summary: str = "",
    epics_dir: str = "",
    epic: str = "",
    repo_dir: str = "",
    repo: str = "",
    area: str = "",
    body: str = "",
) -> FixStorySeed:
    """Register the drawn record as a single-AC story in the perpetual `fixes` bucket."""
    bucket = epic.strip() or "fixes"
    record_id = record_id.strip()
    summary = summary.strip()

    if not record_id:
        logger.warning("no record_id supplied — cannot seed a fix story")
        raise WorkflowFailed(
            "no record_id supplied (expected select_fix_item's record_id output)"
        )
    if not summary:
        logger.warning("no summary supplied — cannot seed a fix story")
        raise WorkflowFailed(
            "no summary supplied (expected select_fix_item's summary output)"
        )

    root = find_docs_root(repo_dir)
    okf = Ostler(root)
    where = (repo, area, body.strip())
    bucket = _ensure_fixes_epic(okf, bucket)
    epic_dir_rel = paths.epic_dir_rel(root, bucket, epics_dir)

    for story in okf.list("story", epic=bucket):
        if record_id not in (story.get("covers") or []):
            continue
        slug = str(story.get("slug", ""))
        path = str(story.get("path", "")) or f"{epic_dir_rel}/stories/{slug}/story.md"
        _author_story_body(root / path, record_id, summary, logger, *where)
        logger.info("story '%s' already covers '%s' — reusing", slug, record_id)
        return FixStorySeed(
            epic=bucket,
            epic_dir=epic_dir_rel,
            story_slug=slug,
            story_id=str(story.get("id", "") or ""),
            story_dir=str(Path(path).parent),
            story_path=path,
            record_id=record_id,
            reason=f"story '{slug}' already covers '{record_id}' — reusing (idempotent)",
        )

    okf.add_seed(
        bucket,
        record_id,
        status="researched",
        summary=summary,
        meta={"sourceRecord": record_id},
    )

    slug = _fix_slug(summary)
    result = okf.create_story(bucket, slug, summary, covers=[record_id])
    if not result.ok:
        raise WorkflowFailed(
            f"could not create fix story '{slug}' in '{bucket}': {result.message}"
        )

    story_dir_rel = f"{epic_dir_rel}/stories/{slug}"
    story_path_rel = f"{story_dir_rel}/story.md"
    _author_story_body(root / story_path_rel, record_id, summary, logger, *where)

    logger.info("registered fix story '%s' covering '%s' in '%s'", slug, record_id, bucket)
    return FixStorySeed(
        epic=bucket,
        epic_dir=epic_dir_rel,
        story_slug=slug,
        story_id=result.entity_id or "",
        story_dir=story_dir_rel,
        story_path=story_path_rel,
        record_id=record_id,
        reason=(
            f"registered fix story '{slug}' ({result.entity_id or '?'}) covering "
            f"'{record_id}' in '{bucket}', authored with a single AC line and its "
            f"filing context"
        ),
    )


def _fix_slug(text: str, *, max_len: int = 60) -> str:
    """The fix story's slug, from its bullet text."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip("-")
    return slug or "fix"


def _ensure_fixes_epic(okf: Ostler, epic: str) -> str:
    """Create the fixes bucket if it is missing; return the directory name it actually has."""
    name = Path(okf.epic_path(epic)).name
    if (okf.root / okf.epic_path(epic) / "epic.md").is_file():
        return name
    result = okf.create_epic(epic, "Coder-filed fixes", followups=True)
    if result.ok:
        return result.entity_name or name
    name = Path(okf.reload().epic_path(epic)).name
    if (okf.root / okf.epic_path(epic) / "epic.md").is_file():
        return name
    raise WorkflowFailed(
        f"could not self-create the '{epic}' epic bucket: {result.message}"
    )


def _fill_empty_section(story_path: Path, heading: str, lines: list[str]) -> bool:
    """Write `lines` under `## <heading>`, but only if that section is still empty."""
    try:
        text = story_path.read_text(encoding="utf-8")
    except OSError:
        return False
    doc = markdown.split(text)
    section = doc.find_section(heading)
    if section is None or not section.is_empty:
        return False
    body = doc.body.split("\n")
    body[section.line_start + 1 : section.line_end] = ["", *lines, ""]
    doc.replace_body(body)
    story_path.write_text(doc.render(), encoding="utf-8")
    return True


def _author_story_body(
    story_path: Path, record_id: str, summary: str, logger: logging.Logger,
    repo: str = "", area: str = "", body: str = "",
) -> None:
    """Write every current required section from the one known fix record."""
    wrote = _fill_empty_section(story_path, "Acceptance Criteria", [f"- {summary}"])
    place = f" in `{repo}/{area}`" if repo and area else ""
    wrote |= _fill_empty_section(
        story_path,
        "Context",
        [
            f"- Filed by QA as debt record `{record_id}`{place} of the artifacts register: "
            f"a defect or gap found while proving another story and left rather than fixed "
            f"in place.",
            "- Scope is that single record and nothing else — one fix, one acceptance "
            "criterion.",
            *(["", *body.splitlines()] if body else []),
        ],
    )
    wrote |= _fill_empty_section(
        story_path,
        "Non-Functional Acceptance Criteria",
        ["(none)"],
    )
    wrote |= _fill_empty_section(
        story_path,
        "Technical Notes",
        ["No prior implementation reference exists."],
    )
    if wrote:
        logger.info(
            "wrote the story body for '%s' from record '%s'",
            story_path.parent.name,
            record_id,
        )


@blueprint.node
def close_fix_item(
    logger: logging.Logger,
    record_id: str = "",
    landed: dict[str, str] | None = None,
    repo_dir: str = "",
) -> FixClosed:
    """Close a drained record as done, naming the commit that fixed it in each repository."""
    record_id = record_id.strip()
    if not record_id or not landed:
        logger.info("no record or no landed commit — nothing to close")
        return FixClosed(record_id=record_id, reason="no record or no landed commit — nothing to close")
    reason = "fixed in " + ", ".join(f"{repo}@{sha[:7]}" for repo, sha in landed.items())
    result = Ostler(find_docs_root(repo_dir)).close_record(record_id, "done", reason)
    if result.ok:
        logger.info("closed '%s' as done: %s", record_id, reason)
    else:
        logger.warning("could not close '%s': %s", record_id, result.message)
    return FixClosed(closed=result.ok, record_id=record_id, reason=result.message)


__all__ = [
    "BacklogBullet",
    "close_fix_item",
    "file_backlog_items",
    "file_deferred_obligations",
    "file_follow_up_backlog",
    "filed_backlog",
    "id_token_set",
    "kebab",
    "norm_desc",
    "seed_fix_story",
    "select_fix_item",
    "unfiled",
]
