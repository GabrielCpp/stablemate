"""The backlog, both ends of it: what the coder files into it, and what it drains back out.

Ports `append-backlog-item.py` (the filing end) and the fix loop's four drain scripts —
`select-next-fix-item.py`, `seed-fix-story.py`, `prune-fix-item.py` and
`mark-fix-blocked.py`.

**The five are one module because they are one contract.** `BACKLOG_ID_RE` is declared
identically in four of the five scripts and `## Filed by coder` in two, and that repetition
is not incidental — a drain that parsed bullets differently from the filer would silently
skip items the filer wrote. The port has one definition of each, which is the only way to
make that class of drift impossible rather than merely unlikely.

*Filing*: when implement, review or QA finds work that is genuinely *separate* scope, it
writes the item to `<spec_dir>/backlog-items.json`; `file_backlog_items` appends it to
`docs/backlog.md` so the author workflow authors it next run. A coder-filed `[id]` is a
valid owner for a `deferred` gap, which is how the author's coverage gate resolves and the
loop closes. The guardrail that keeps this from becoming a dumping ground lives in the
prompts, not here: a buildable in-scope precondition is *built* by the implementer, never
punted.

*Draining*: `select_fix_item` draws the first unblocked bullet under `## Filed by coder`,
`seed_fix_story` turns it into a single-AC story in the perpetual `fixes` bucket, and the
iteration ends at `prune_fix_item` (shipped) or `mark_fix_blocked` (stuck). Blocking
annotates in place rather than removing, so the item stays visible to a human while every
later draw skips it — which is what keeps a permanently-stuck fix from spinning the loop.

Nothing changes about the rules on either end — the three de-dup signals, the section
placement, the backlog scaffold, the reconciled-items unlink, the selection predicate, the
idempotent story reuse and the never-clobber section writes are all as written. What
changes is what a failure does: the scripts printed a note to stderr and carried on, and a
node logs it, because a run record that names the node is the whole point of having one.
The four `scriptutil.die(…, code=2)` calls in `seed-fix-story.py` become `WorkflowFailed`,
which is the same non-zero exit routed through the driver's own failure path.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from ostler import Ostler, markdown
from workhorse.pyflow import WorkflowFailed
from workhorse.scriptutil import find_docs_root
from workhorse_workflows.coder.nodes._blueprint import blueprint
from workhorse_workflows.coder.schemas.backlog import (
    FixBlocked,
    FixPick,
    FixPruned,
    FixStorySeed,
)
from workhorse_workflows.coder.schemas.qa import BacklogDrain

#: The backlog's bullet grammar: `- [kebab-id] one self-contained line`.
BACKLOG_ID_RE = re.compile(r"^\s*-\s*\[([A-Za-z0-9][A-Za-z0-9._-]*)\]\s*(.*)$")

#: Where an item lands when it names no section of its own, created once per backlog.
FILED_HEADING = "## Filed by coder"

#: A trailing `(blocked: …)` annotation is `mark-fix-blocked.py`'s, not part of the item's
#: identity — stripped before comparing descriptions so a re-file still de-dups against it.
BLOCKED_SUFFIX_RE = re.compile(r"\s*\(blocked\b.*$", re.IGNORECASE)

#: The backlog itself. Repo-relative: the node joins it onto a freshly resolved docs root.
BACKLOG_REL = "docs/backlog.md"


def kebab(raw: str) -> str:
    """Sanitize an id to a stable kebab handle (the backlog's `[id]` grammar)."""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", str(raw).strip().lower()).strip("-")


def norm_desc(desc: str) -> str:
    """Normalize a description to an identity key; empty means "never matches"."""
    text = BLOCKED_SUFFIX_RE.sub("", str(desc or ""))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def id_token_set(item_id: str) -> frozenset[str]:
    """The tokens of a kebab id, order-insensitive, so a word-permuted re-file collides."""
    return frozenset(t for t in re.split(r"[.\-_]+", str(item_id or "").lower()) if t)


class Seen:
    """The three high-precision de-dup signals, seeded from the backlog and grown per batch.

    All three are exact matches, not fuzzy, and that is the trade the script chose
    deliberately: two items that merely share some words are *not* merged, because dropping
    genuinely-separate scope is worse than filing a near-duplicate — the author's coverage
    gate depends on filed items existing.
    """

    def __init__(self, lines: list[str]) -> None:
        self.ids: set[str] = set()
        self.descs: set[str] = set()
        self.idsets: set[frozenset[str]] = set()
        for line in lines:
            match = BACKLOG_ID_RE.match(line)
            if match:
                self.add(match.group(1), match.group(2))

    def add(self, item_id: str, desc: str) -> None:
        """Record an item so the rest of the batch de-dups against it too."""
        if item_id:
            self.ids.add(item_id)
            tokens = id_token_set(item_id)
            if tokens:
                self.idsets.add(tokens)
        key = norm_desc(desc)
        if key:
            self.descs.add(key)

    def duplicate(self, item_id: str, desc: str) -> bool:
        """Same id, same id-token-set, or same normalized description."""
        if item_id and item_id in self.ids:
            return True
        tokens = id_token_set(item_id)
        if tokens and tokens in self.idsets:
            return True
        key = norm_desc(desc)
        return bool(key and key in self.descs)


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


def _insert_under_section(lines: list[str], section: str, bullet: str) -> list[str]:
    """Append `bullet` to the named `## section`, or under `## Filed by coder` at the end."""
    if section:
        target = section.strip().lstrip("#").strip().lower()
        for index, line in enumerate(lines):
            if line.lstrip().startswith("#") and line.lstrip("#").strip().lower() == target:
                end = index + 1
                while end < len(lines) and not lines[end].lstrip().startswith("#"):
                    end += 1
                while end > index + 1 and not lines[end - 1].strip():
                    end -= 1
                lines.insert(end, bullet)
                return lines

    if not any(line.strip() == FILED_HEADING for line in lines):
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(FILED_HEADING)
        lines.append("")
    lines.append(bullet)
    return lines


@blueprint.node
def file_backlog_items(
    logger: logging.Logger, spec_dir: str = "", docs_path: str = "", repo_dir: str = ""
) -> BacklogDrain:
    """Append this story's filed items to the repo backlog, de-duplicated, then clear them.

    The items file is removed once reconciled — every item either appended or already
    present — so a rerun cannot re-file them. It is kept only when the backlog could not be
    created at all, which is the one path where the items would otherwise be lost.
    """
    root = find_docs_root(docs_path, repo_dir)
    spec = spec_dir.strip()
    if not spec:
        logger.info("no spec_dir supplied — nothing to drain")
        return BacklogDrain(notes="no spec_dir supplied — nothing to drain")

    items_path = root / spec / "backlog-items.json"
    items = _load_items(logger, items_path)
    if not items:
        logger.info("no backlog items to file at %s", items_path)
        return BacklogDrain(notes="no backlog items to file")

    backlog_path = root / BACKLOG_REL
    if not backlog_path.is_file():
        try:
            backlog_path.parent.mkdir(parents=True, exist_ok=True)
            backlog_path.write_text("# Backlog\n", encoding="utf-8")
        except OSError as exc:
            logger.warning("could not create backlog at %s: %s", BACKLOG_REL, exc)
            return BacklogDrain(
                skipped=len(items),
                notes=(
                    f"no backlog at {BACKLOG_REL} and could not create it — "
                    f"{len(items)} item(s) not filed (items file kept)"
                ),
            )

    lines = backlog_path.read_text(encoding="utf-8").splitlines()
    seen = Seen(lines)

    appended = 0
    skipped = 0
    for item in items:
        item_id = kebab(item.get("id") or "")
        desc = str(item.get("description") or "").strip().replace("\n", " ")
        if not item_id or not desc or seen.duplicate(item_id, desc):
            skipped += 1
            continue
        lines = _insert_under_section(lines, str(item.get("section") or ""), f"- [{item_id}] {desc}")
        seen.add(item_id, desc)
        appended += 1

    if appended:
        backlog_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    try:
        items_path.unlink()
        removed = True
    except OSError as exc:
        logger.warning("could not remove items file: %s", exc)
        removed = False

    note = f"filed {appended}, skipped {skipped} (duplicate/invalid)"
    note += "; removed backlog-items.json" if removed else "; backlog-items.json left in place"
    logger.info(note)
    return BacklogDrain(appended=appended, skipped=skipped, notes=note)


# ── Draining it: the fix loop's worklist ─────────────────────────────────────────────


@blueprint.node
def select_fix_item(
    logger: logging.Logger, docs_path: str = "", backlog_path: str = "", repo_dir: str = ""
) -> FixPick:
    """Draw the next drainable bullet from `## Filed by coder`, or report the pool dry.

    "Drainable" is the first bullet whose line does not already carry a `(blocked` marker
    and that has both an id and text. Selection only — the file is not touched here, which
    is what lets a resumed iteration re-draw the same item and reach the same story.
    """
    rel = backlog_path.strip() or BACKLOG_REL
    root = find_docs_root(docs_path, repo_dir)
    path = root / rel

    if not path.is_file():
        logger.info("no backlog file at %s — nothing to drain", rel)
        return FixPick(reason=f"no backlog file at {rel} — nothing to drain")

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        logger.warning("could not read %s: %s", rel, exc)
        return FixPick(reason=f"could not read {rel}: {exc}")

    section = _filed_section(lines)
    if not section:
        logger.info("no '%s' section — nothing to drain", FILED_HEADING)
        return FixPick(reason=f"no '{FILED_HEADING}' section — nothing to drain")

    for line in section:
        match = BACKLOG_ID_RE.match(line)
        if not match or "(blocked" in line:
            continue
        bullet_id, text = match.group(1).strip(), match.group(2).strip()
        if not bullet_id or not text:
            continue
        logger.info("drew '%s' from '%s'", bullet_id, FILED_HEADING)
        return FixPick(
            has_fix=True,
            fix_bullet_id=bullet_id,
            fix_bullet_text=text,
            reason=f"drew '{bullet_id}' from '{FILED_HEADING}'",
        )

    logger.info("'%s' has no drainable bullet (empty or all blocked)", FILED_HEADING)
    return FixPick(
        reason=f"'{FILED_HEADING}' has no drainable bullet (empty or all blocked)"
    )


def _filed_section(lines: list[str]) -> list[str]:
    """The lines under `## Filed by coder`, heading excluded, up to the next `#` or EOF."""
    for index, line in enumerate(lines):
        if line.strip() == FILED_HEADING:
            end = index + 1
            while end < len(lines) and not lines[end].lstrip().startswith("#"):
                end += 1
            return lines[index + 1 : end]
    return []


@blueprint.node
def seed_fix_story(
    logger: logging.Logger,
    bullet_id: str = "",
    bullet_text: str = "",
    epics_dir: str = "",
    epic: str = "",
    docs_path: str = "",
    repo_dir: str = "",
) -> FixStorySeed:
    """Register the drawn bullet as a single-AC story in the perpetual `fixes` bucket.

    The twin of author mode's `seed-story.py`, with two deliberate differences. That one
    hard-fails when its epic does not exist, because an operator was meant to create it;
    the fix loop has no operator step, so it self-creates the `fixes` bucket the first time
    it is needed. And the bucket is never registered in the epics queue, so epic-mode
    selection can never pick it up.

    **This node is the story's author, not just its scaffolder.** `okf.create_story`
    scaffolds the required sections *empty*, and an empty section is an unwritten story —
    `Story.authored` is false, `ostler doctor` files `unwritten-story`, and story prep
    refuses to plan against it. So both sections are written here: the bullet becomes the
    single `## Acceptance Criteria` line (the literal enactment of "one fix, one AC"), and
    `## Context` records where it came from, which is the whole of what is known about a
    filed fix. Thin on purpose, and still authored.
    """
    epics_rel = epics_dir.strip() or "docs/epics"
    bucket = epic.strip() or "fixes"
    bullet_id = bullet_id.strip()
    bullet_text = bullet_text.strip()

    if not bullet_id:
        logger.warning("no bullet_id supplied — cannot seed a fix story")
        raise WorkflowFailed(
            "no bullet_id supplied (expected select_fix_item's fix_bullet_id output)"
        )
    if not bullet_text:
        logger.warning("no bullet_text supplied — cannot seed a fix story")
        raise WorkflowFailed(
            "no bullet_text supplied (expected select_fix_item's fix_bullet_text output)"
        )

    root = find_docs_root(docs_path, repo_dir)
    okf = Ostler(root)
    # The bucket's directory name is ostler's answer, not the slug asked for: epic
    # directories are numbered (`0001-fixes`), so joining `epics_dir` with the bare bucket
    # slug names a directory that does not exist. `epics_dir` still says which root.
    bucket = _ensure_fixes_epic(okf, bucket)
    epic_dir_rel = f"{epics_rel}/{bucket}"

    # Idempotent: if a story already covers this id, reuse it (resumable rerun).
    for story in okf.list("story", epic=bucket):
        if bullet_id not in (story.get("covers") or []):
            continue
        slug = str(story.get("slug", ""))
        path = str(story.get("path", "")) or f"{epic_dir_rel}/stories/{slug}/story.md"
        _author_story_body(root / path, bullet_id, bullet_text, logger)
        logger.info("story '%s' already covers '%s' — reusing", slug, bullet_id)
        return FixStorySeed(
            epic=bucket,
            epic_dir=epic_dir_rel,
            story_slug=slug,
            story_dir=str(Path(path).parent),
            story_path=path,
            bullet_id=bullet_id,
            reason=f"story '{slug}' already covers '{bullet_id}' — reusing (idempotent)",
        )

    okf.add_seed(
        bucket,
        bullet_id,
        status="researched",
        summary=bullet_text,
        meta={"sourceBullet": bullet_text},
    )

    slug = _fix_slug(bullet_text)
    result = okf.create_story(bucket, slug, bullet_text, covers=[bullet_id])
    if not result.ok:
        raise WorkflowFailed(
            f"could not create fix story '{slug}' in '{bucket}': {result.message}"
        )

    story_dir_rel = f"{epic_dir_rel}/stories/{slug}"
    story_path_rel = f"{story_dir_rel}/story.md"
    _author_story_body(root / story_path_rel, bullet_id, bullet_text, logger)

    logger.info("registered fix story '%s' covering '%s' in '%s'", slug, bullet_id, bucket)
    return FixStorySeed(
        epic=bucket,
        epic_dir=epic_dir_rel,
        story_slug=slug,
        story_dir=story_dir_rel,
        story_path=story_path_rel,
        bullet_id=bullet_id,
        reason=(
            f"registered fix story '{slug}' ({result.entity_id or '?'}) covering "
            f"'{bullet_id}' in '{bucket}', authored with a single AC line and its "
            f"filing context"
        ),
    )


def _fix_slug(text: str, *, max_len: int = 60) -> str:
    """The fix story's slug, from its bullet text.

    Not `kebab` above: that one sanitizes an already-chosen *id* and keeps `.` and `_`,
    while this one turns a sentence into a bounded handle. The scripts had two functions of
    the same name doing these two different jobs, and merging them would change one of the
    two behaviors.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip("-")
    return slug or "fix"


def _ensure_fixes_epic(okf: Ostler, epic: str) -> str:
    """Create the fixes bucket if it is missing; return the directory name it actually has.

    That name is not necessarily the one asked for: ostler numbers epic directories in
    creation order, so the `fixes` bucket is `0004-fixes` in a repo with three epics before
    it. Every ostler call still takes the bare slug; it is the *paths* built from it that
    have to use the real name.

    Idempotent both before and after the call. The second existence check is not redundant:
    a prior or concurrent run may have created the epic between the first check and
    `create_epic`, and an "already exists" result is success here, not an error.
    """
    name = Path(okf.epic_path(epic)).name
    if (okf.root / okf.epic_path(epic) / "epic.md").is_file():
        return name
    result = okf.create_epic(epic, "Coder-filed fixes")
    if result.ok:
        return result.entity_name or name
    name = Path(okf.reload().epic_path(epic)).name
    if (okf.root / okf.epic_path(epic) / "epic.md").is_file():
        return name
    raise WorkflowFailed(
        f"could not self-create the '{epic}' epic bucket: {result.message}"
    )


def _fill_empty_section(story_path: Path, heading: str, lines: list[str]) -> bool:
    """Write `lines` under `## <heading>`, but only if that section is still empty.

    Located through ostler's markdown parser (`Section.is_empty` — the same predicate
    `Story.authored` and `doctor` use), never by scanning the rendered text: a section is
    empty when it carries no prose of its own or in its sub-sections, which is exactly the
    question "has anybody written this yet?". A section somebody has already written is
    left byte-identical, so a resumed run neither duplicates nor clobbers.
    """
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
    story_path: Path, bullet_id: str, bullet_text: str, logger: logging.Logger
) -> None:
    """Write the fix story's two required sections: its single AC, and where it came from."""
    wrote = _fill_empty_section(story_path, "Acceptance Criteria", [f"- {bullet_text}"])
    wrote |= _fill_empty_section(
        story_path,
        "Context",
        [
            f"- Filed by the coder workflow as backlog item `{bullet_id}` in "
            f"`{BACKLOG_REL}` under `{FILED_HEADING}`: a defect or gap found while working "
            f"on another story and deferred rather than fixed in place.",
            "- Scope is that single item and nothing else — one fix, one acceptance "
            "criterion.",
        ],
    )
    if wrote:
        logger.info(
            "wrote the story body for '%s' from backlog item '%s'",
            story_path.parent.name,
            bullet_id,
        )


@blueprint.node
def prune_fix_item(
    logger: logging.Logger,
    bullet_id: str = "",
    docs_path: str = "",
    backlog_path: str = "",
    repo_dir: str = "",
) -> FixPruned:
    """Remove a shipped fix's bullet from the backlog. Ostler first, direct edit second.

    `okf.backlog_prune` already matches `- [<id>] …` anywhere in the file and rewrites it
    without the line, so it is the primary path. The regex fallback covers a custom
    `backlog_path` layout ostler does not know to look at — a mechanical removal it could
    do itself should never hard-stop the drain loop.
    """
    bullet_id = bullet_id.strip()
    rel = backlog_path.strip() or BACKLOG_REL

    if not bullet_id:
        logger.info("no bullet_id supplied — nothing to prune")
        return FixPruned(reason="no bullet_id supplied — nothing to prune")

    root = find_docs_root(docs_path, repo_dir)
    if Ostler(root).backlog_prune(bullet_id).ok:
        logger.info("pruned '%s' via ostler", bullet_id)
        return FixPruned(
            pruned=True, bullet_id=bullet_id, reason=f"pruned '{bullet_id}' via ostler"
        )

    if _prune_via_regex(root / rel, bullet_id):
        logger.info("pruned '%s' via direct edit", bullet_id)
        return FixPruned(
            pruned=True,
            bullet_id=bullet_id,
            reason=f"pruned '{bullet_id}' via direct edit",
        )

    logger.warning("no backlog bullet '%s' found to prune", bullet_id)
    return FixPruned(
        bullet_id=bullet_id, reason=f"no backlog bullet '{bullet_id}' found to prune"
    )


def _prune_via_regex(path: Path, bullet_id: str) -> bool:
    """Drop every `- [bullet_id] …` line from the file. False when there was nothing to drop."""
    if not path.is_file():
        return False
    kept: list[str] = []
    removed = False
    for line in path.read_text(encoding="utf-8").splitlines():
        match = BACKLOG_ID_RE.match(line)
        if match and match.group(1).strip() == bullet_id:
            removed = True
            continue
        kept.append(line)
    if removed:
        path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return removed


@blueprint.node
def mark_fix_blocked(
    logger: logging.Logger,
    bullet_id: str = "",
    note: str = "",
    docs_path: str = "",
    backlog_path: str = "",
    repo_dir: str = "",
) -> FixBlocked:
    """Annotate a stuck fix in place instead of pruning it — the drain's "flag and continue".

    The fix-loop counterpart of epic mode's QA give-up. A fix that still fails after its one
    bounded retry is neither deleted (a human should still see it) nor retried forever (it
    would stall the drain): it is annotated `(blocked: …)`, which `select_fix_item` skips on
    every future draw while it stays visible in the backlog.

    Ostler has no verb for this — only add/prune/list exist for backlog items — so the file
    is edited directly, under the same bullet-line contract the rest of this module uses.
    """
    bullet_id = bullet_id.strip()
    reason_note = note.strip() or "qa failed after retry"
    rel = backlog_path.strip() or BACKLOG_REL

    if not bullet_id:
        logger.warning("no bullet_id supplied — nothing to mark")
        return FixBlocked(reason="no bullet_id supplied — nothing to mark")

    root = find_docs_root(docs_path, repo_dir)
    path = root / rel
    if not path.is_file():
        logger.warning("no backlog file at %s", rel)
        return FixBlocked(bullet_id=bullet_id, reason=f"no backlog file at {rel}")

    lines = path.read_text(encoding="utf-8").splitlines()
    changed = False
    found = False
    for index, line in enumerate(lines):
        match = BACKLOG_ID_RE.match(line)
        if not match or match.group(1).strip() != bullet_id:
            continue
        found = True
        if "(blocked" in line:
            break  # already annotated — idempotent no-op
        lines[index] = f"{line.rstrip()} (blocked: {reason_note})"
        changed = True
        break

    if not found:
        logger.warning("no backlog bullet '%s' found to mark", bullet_id)
        return FixBlocked(
            bullet_id=bullet_id, reason=f"no backlog bullet '{bullet_id}' found to mark"
        )

    if changed:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        logger.info("marked '%s' blocked: %s", bullet_id, reason_note)
        return FixBlocked(
            marked=True,
            bullet_id=bullet_id,
            reason=f"marked '{bullet_id}' blocked: {reason_note}",
        )

    logger.info("'%s' already marked blocked (no-op)", bullet_id)
    return FixBlocked(
        marked=True,
        bullet_id=bullet_id,
        reason=f"'{bullet_id}' already marked blocked (no-op)",
    )


__all__ = [
    "BACKLOG_ID_RE",
    "Seen",
    "file_backlog_items",
    "id_token_set",
    "kebab",
    "mark_fix_blocked",
    "norm_desc",
    "prune_fix_item",
    "seed_fix_story",
    "select_fix_item",
]
