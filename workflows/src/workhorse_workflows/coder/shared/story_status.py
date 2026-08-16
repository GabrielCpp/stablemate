"""Stamp a story's Status — the single place the coder workflow records an outcome.

Ports `scripts/story_status.py`, which was a helper module rather than a node: two nodes
call it, and neither of them is *about* status.

Story selection reads the status, not the git log: `ostler next-story` reads the story.md
**frontmatter** `status:` field, falling back to the body's `- **Status**:` line. So a story
whose status is never written is, to every later loop iteration, still open — it gets re-selected,
re-planned and re-QA'd, and its epic never reads as complete.

Both outcome paths therefore go through here:

* the success path (`commit_story`) — `QA passed`.

There is no longer a second, give-up path: a story that does not pass QA ends the run
with nothing committed and nothing stamped, so the only status this writes is a true one.

`Ostler.set_status` writes BOTH the frontmatter and the body line, and locates that line
through ostler's markdown parser, which is why it is **the** path. The body-only rewrite
below is the fallback of last resort, for the one case where the doc graph cannot resolve
the slug at all — a story.md with no frontmatter, or a non-standard layout (the workflow
test sandboxes are exactly this). It locates the field with ostler's parser too, so the two
paths write the same line. There is no ostler-is-missing path: the workflow declares
`dist: ostler` in its `requires:` block, so an interpreter that cannot import it never
reaches node one.

The caller is responsible for committing the returned paths; leaving a stamped status
uncommitted is what makes a resumed run re-litigate a finished story.

**One thing changes in the port.** Both callers reached this module through
`scriptutil.fresh_import("story_status", also_purge=("ostler",))` — a re-import per call,
so that a mid-run edit to ostler (an environment-fix loop landing a change while QA nodes
are still ahead in the graph) was not shadowed by the copy an earlier node had cached in
`sys.modules`. That was only ever needed because each node was a separate *script* import;
under the driver every node in a run shares one interpreter and one import of this module,
so a plain module-scope import is the port. The behavior it bought — a mid-run ostler edit
taking effect in the same run — is genuinely gone, and it is recorded as a finding rather
than passed over. It never applied to `research`, `author` or `okf-builder`, none of which
re-imported anything.
"""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from ostler import Ostler, markdown, path as okf_path
from ostler.model import status_bullet, story_status

#: The literal an append writes when the story carries no Status field yet. Reading one is
#: ostler's parser's job, never a scan for this string.
STATUS_PREFIX = "- **Status**:"

_logger = logging.getLogger(__name__)


def resolve_story_path(root: Path, epic: str, slug: str, story_path_arg: str = "") -> Path:
    """The story.md to fall back to when ostler cannot resolve the slug."""
    if story_path_arg and Path(story_path_arg).is_file():
        return Path(story_path_arg)
    return okf_path.story_dir_in(root, epic, slug) / "story.md"


def mark_via_ostler(
    root: Path, slug: str, new_status: str, logger: logging.Logger | None = None
) -> list[Path]:
    """Set the status through the doc graph. Returns the paths written (empty on failure).

    A graph that will not load at this root is the only fallback trigger — an ostler that
    will not *import* is not survivable here and is not survived: the workflow's
    `requires:` preflight refuses to start the run.
    """
    log = logger or _logger
    if not slug:
        return []
    try:
        res = Ostler(root).set_status(slug, new_status)
    except (OSError, ValueError, RuntimeError) as exc:
        log.info("ostler set-status unavailable for %s (%s) — falling back to story.md", slug, exc)
        return []
    if not res.ok:
        log.info("ostler set-status failed for %s: %s — falling back to story.md", slug, res.message)
        return []
    return list(res.paths)


def status_line_index(text: str) -> int | None:
    """Index of the line carrying the story's Status field, or `None` if it has none.

    Located through ostler's parser — the same `Bullet` lookup `crud.set_status` uses, so
    `- Status:` and `- **Status**:` are one field and a "Status" in the prose is not one.
    The document is never pattern-matched.
    """
    doc = markdown.split(text)
    bullet = status_bullet(doc)
    return doc.body_offset + bullet.line_start if bullet is not None else None


def rewrite_status(
    story_md: Path, new_status: str, logger: logging.Logger | None = None
) -> list[Path]:
    """Rewrite (or append) the body's `- **Status**:` line. Returns the path written."""
    log = logger or _logger
    text = story_md.read_text(encoding="utf-8")
    idx = status_line_index(text)
    if idx is not None:
        # Rewrite via a temp file + os.replace rather than editing in place, so a write
        # failure cannot leave story.md half-written (portable equivalent of the bash
        # original's mktemp+mv, which existed to dodge GNU/BSD `sed -i` incompatibilities
        # entirely).
        lines = text.split("\n")
        head, sep, _ = lines[idx].partition(":")
        lines[idx] = f"{head}: {new_status}" if sep else f"{STATUS_PREFIX} {new_status}"
        new_text = "\n".join(lines)
        fd, tmp_name = tempfile.mkstemp(dir=story_md.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(new_text)
            os.replace(tmp_name, story_md)
        except OSError:
            os.unlink(tmp_name)
            log.warning("could not rewrite Status in %s", story_md)
            return []
    else:
        with story_md.open("a", encoding="utf-8") as f:
            f.write(f"{STATUS_PREFIX} {new_status}\n")
    return [story_md]


def current(
    root: Path,
    slug: str,
    *,
    epic: str = "",
    story_path: str = "",
) -> str:
    """What the story.md says its status is right now, `""` when it says nothing.

    The counterpart of `mark`, and the same field: `ostler.model.story_status` reads the
    frontmatter first and the parsed `- **Status**:` bullet second, so this answers with
    exactly the value `set_status` would overwrite — never a substring of the prose. A
    caller compares it against the status it is about to write to learn whether the stamp
    is a change or a no-op.
    """
    story_md = resolve_story_path(root, epic, slug, story_path)
    if not story_md.is_file():
        return ""
    try:
        text = story_md.read_text(encoding="utf-8")
    except OSError:
        return ""
    return story_status(markdown.split(text))


def mark(
    root: Path,
    slug: str,
    new_status: str,
    *,
    epic: str = "",
    story_path: str = "",
    logger: logging.Logger | None = None,
) -> list[Path]:
    """Stamp `slug`'s status, graph-first. Returns the paths written (empty if none).

    Never raises: an unstampable status is a degraded run, not a reason to end one — the
    caller's own belt-and-braces (the per-run skip set on the give-up path, the epic's
    commit history on the success path) still applies.
    """
    log = logger or _logger
    written = mark_via_ostler(root, slug, new_status, log)
    if written:
        return written

    story_md = resolve_story_path(root, epic, slug, story_path)
    if not story_md.is_file():
        log.warning("no story.md for %s — status '%s' NOT recorded", slug, new_status)
        return []
    return rewrite_status(story_md, new_status, log)


__all__ = [
    "STATUS_PREFIX",
    "current",
    "mark",
    "mark_via_ostler",
    "resolve_story_path",
    "rewrite_status",
    "status_line_index",
]
