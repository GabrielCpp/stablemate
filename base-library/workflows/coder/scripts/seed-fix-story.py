#!/usr/bin/env python3
"""Register ONE drained backlog bullet as a single-AC story in the `fixes` bucket — ostler-backed.

Twin of `author/scripts/seed-story.py`, adapted for the coder fix loop:

- Story mode's `seed-story.py` hard-fails if its target epic doesn't already exist (an operator
  must have created it). The fix loop has no such operator step — it self-creates a small,
  perpetual `fixes` epic bucket the first time it's needed (idempotent: an "already exists"
  result from `okf.create_epic` is treated as success, not an error). This bucket is never
  registered in the epics queue (`okf.todo_add`) that `select_epic`/`prune_epic` manage, so it
  never collides with or gets picked up by epic-mode story selection.
- The bullet id/text are handed in directly by `select-next-fix-item.py`'s output (it already did
  the backlog scan), so there's no `resolve_bullet()` re-parse step here.
- `okf.create_story` scaffolds story.md's required sections *empty*, and an empty section is an
  unwritten story: `Story.authored` is false, `ostler doctor` files `unwritten-story`, and
  `prepare-story.py` refuses to plan against it. This script is the story's author, so it writes
  both — `## Acceptance Criteria` gets the bullet text as the SINGLE AC line (the literal
  enactment of "1 fix = 1 AC"), and `## Context` gets where the bullet came from, which is the
  whole of what is known about a filed fix. A seeded fix story is therefore authored the moment
  it exists; nothing downstream has to special-case it.

Idempotent / resumable: if a story already covers the bullet id, that story is reused rather than
created again, and an already-written section is never overwritten.

Mutates the doc graph through the in-process `ostler` Python API (`from ostler import Ostler`).

Args:
    argv[1]  bullet_id    : the backlog item id (required, from select-next-fix-item.py)
    argv[2]  bullet_text  : the backlog item text (required, from select-next-fix-item.py)
    argv[3]  epics_dir    : repo-relative epics root (default docs/epics)
    argv[4]  epic         : the fix-stories epic bucket name (default "fixes")
    argv[5]  docs_path    : optional explicit docs root override (passed to find_docs_root)

Outputs JSON: {"epic": "...", "epic_dir": "...", "story_slug": "...", "story_dir": "...",
               "story_path": "...", "bullet_id": "...", "reason": "..."}
"""
from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path
from typing import NoReturn

from ostler import Ostler, markdown

from workhorse import scriptutil


def die(msg: str) -> NoReturn:
    scriptutil.die(f"seed-fix-story: {msg}", code=2)


def kebab(text: str, *, max_len: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip("-")
    return slug or "fix"


def emit(**kwargs: str) -> None:
    payload = {
        "epic": "", "epic_dir": "", "story_slug": "", "story_dir": "", "story_path": "",
        "bullet_id": "", "reason": "",
    }
    payload.update(kwargs)
    print(json.dumps(payload))
    sys.exit(0)


def ensure_fixes_epic(okf: Ostler, epics_dir_rel: str, epic: str) -> None:
    epic_dir = okf.root / epics_dir_rel / epic
    if (epic_dir / "epic.md").is_file():
        return
    res = okf.create_epic(epic, "Coder-filed fixes")
    if res.ok:
        return
    # Idempotent: a concurrent/prior run may have created it between our check and this call.
    if (epic_dir / "epic.md").is_file():
        return
    die(f"could not self-create the '{epic}' epic bucket: {res.message}")


def fill_empty_section(story_path: Path, heading: str, lines: list[str]) -> bool:
    """Write `lines` under `## <heading>`, but only if that section is still empty.

    Located through ostler's markdown parser (`Section.is_empty` — the same predicate
    `Story.authored` and `doctor` use), never by scanning the rendered text: a section is
    empty when it carries no prose of its own or in its sub-sections, which is exactly the
    question "has anybody written this yet?". A section somebody has already written is left
    byte-identical, so a resumed run neither duplicates nor clobbers.
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
    body[section.line_start + 1:section.line_end] = ["", *lines, ""]
    doc.replace_body(body)
    story_path.write_text(doc.render(), encoding="utf-8")
    return True


def author_story_body(story_path: Path, bullet_id: str, bullet_text: str, logger: logging.Logger,
                      *, backlog_rel: str = "docs/backlog.md") -> None:
    """Write the story's required sections — the seeding script *is* this story's author.

    A fix story has no discovery phase behind it: everything known about it is the one backlog
    bullet the coder filed, so Context says where the bullet came from and Acceptance Criteria
    is the bullet itself. That is thin on purpose, and it is still a written story rather than
    a scaffold — the distinction the fail-closed gate in `prepare-story.py` turns on.
    """
    wrote = fill_empty_section(story_path, "Acceptance Criteria", [f"- {bullet_text}"])
    wrote |= fill_empty_section(story_path, "Context", [
        f"- Filed by the coder workflow as backlog item `{bullet_id}` in "
        f"`{backlog_rel}` under `## Filed by coder`: a defect or gap found while working on "
        f"another story and deferred rather than fixed in place.",
        "- Scope is that single item and nothing else — one fix, one acceptance criterion.",
    ])
    if wrote:
        logger.info("wrote the story body for '%s' from backlog item '%s'",
                    story_path.parent.name, bullet_id)


def main(logger: logging.Logger) -> None:
    bullet_id = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else ""
    bullet_text = sys.argv[2].strip() if len(sys.argv) > 2 and sys.argv[2] else ""
    epics_dir_rel = (sys.argv[3].strip() if len(sys.argv) > 3 and sys.argv[3] else "") or "docs/epics"
    epic = (sys.argv[4].strip() if len(sys.argv) > 4 and sys.argv[4] else "") or "fixes"
    docs_path_arg = sys.argv[5] if len(sys.argv) > 5 else ""

    if not bullet_id:
        logger.warning("no bullet_id supplied — cannot seed a fix story")
        die("no bullet_id supplied (expected select-next-fix-item.py's fix_bullet_id output)")
    if not bullet_text:
        logger.warning("no bullet_text supplied — cannot seed a fix story")
        die("no bullet_text supplied (expected select-next-fix-item.py's fix_bullet_text output)")

    root = scriptutil.find_docs_root(docs_path_arg)
    okf = Ostler(root)
    epic_dir_rel = f"{epics_dir_rel}/{epic}"

    ensure_fixes_epic(okf, epics_dir_rel, epic)

    # Idempotent: if a story already covers this id, reuse it (resumable rerun).
    stories = okf.list("story", epic=epic)
    for s in stories:
        if bullet_id in (s.get("covers") or []):
            slug = str(s.get("slug", ""))
            path = str(s.get("path", "")) or f"{epic_dir_rel}/stories/{slug}/story.md"
            story_path = root / path
            author_story_body(story_path, bullet_id, bullet_text, logger)
            logger.info("story '%s' already covers '%s' — reusing", slug, bullet_id)
            emit(epic=epic, epic_dir=epic_dir_rel, story_slug=slug,
                 story_dir=str(Path(path).parent), story_path=path, bullet_id=bullet_id,
                 reason=f"story '{slug}' already covers '{bullet_id}' — reusing (idempotent)")

    okf.add_seed(epic, bullet_id, status="researched", summary=bullet_text,
                 meta={"sourceBullet": bullet_text})

    slug = kebab(bullet_text)
    res = okf.create_story(epic, slug, bullet_text, covers=[bullet_id])
    if not res.ok:
        die(f"could not create fix story '{slug}' in '{epic}': {res.message}")

    story_dir_rel = f"{epic_dir_rel}/stories/{slug}"
    story_path_rel = f"{story_dir_rel}/story.md"
    author_story_body(root / story_path_rel, bullet_id, bullet_text, logger)

    logger.info("registered fix story '%s' covering '%s' in '%s'", slug, bullet_id, epic)
    emit(epic=epic, epic_dir=epic_dir_rel, story_slug=slug, story_dir=story_dir_rel,
         story_path=story_path_rel, bullet_id=bullet_id,
         reason=f"registered fix story '{slug}' ({res.entity_id or '?'}) covering '{bullet_id}' "
                f"in '{epic}', authored with a single AC line and its filing context")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("seed-fix-story"))
