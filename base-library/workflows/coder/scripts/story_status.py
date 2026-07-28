#!/usr/bin/env python3
"""Stamp a story's Status — the single place the coder workflow records an outcome.

Story selection reads the status, not the git log: ``ostler next-story`` (the
PRIMARY selector) reads the story.md **frontmatter** ``status:`` field, and
``select-next-story.py``'s dependencies.json fallback reads the body's
``- **Status**:`` line. So a story whose status is never written is, to every
later loop iteration, still open — it gets re-selected, re-planned and re-QA'd,
and its epic never reads as complete.

Both outcome paths therefore go through here:

* the give-up path (``flag-qa-failure.py``) — an honest "did not pass" marker;
* the success path (``commit-story.py``) — ``QA passed``.

``Ostler.set_status`` writes BOTH the frontmatter and the body line, which is why
it is tried first. The body-only rewrite is the fallback for the cases where the
doc graph can't resolve the slug at all — a story.md with no frontmatter, or a
non-standard layout (the workflow test sandboxes are exactly this).

The caller is responsible for committing the returned paths; leaving a stamped
status uncommitted is what makes a resumed run re-litigate a finished story.
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path

STATUS_LINE_RE = re.compile(r"^- \*\*Status\*\*:.*$", re.MULTILINE)

_logger = logging.getLogger("story-status")


def resolve_story_path(root: Path, epic: str, slug: str, story_path_arg: str = "") -> Path:
    """The story.md to fall back to when ostler can't resolve the slug."""
    if story_path_arg and Path(story_path_arg).is_file():
        return Path(story_path_arg)
    return root / "docs" / "epics" / epic / "stories" / slug / "story.md"


def mark_via_ostler(root: Path, slug: str, new_status: str,
                    logger: logging.Logger | None = None) -> list[Path]:
    """Set the status through the doc graph. Returns the paths written (empty on failure).

    Imported lazily so a caller that never reaches this path (no slug, no graph)
    doesn't pay for loading the graph machinery.
    """
    log = logger or _logger
    if not slug:
        return []
    try:
        from ostler import Ostler

        res = Ostler(root).set_status(slug, new_status)
    except (ImportError, OSError, ValueError, RuntimeError) as exc:
        log.info("ostler set-status unavailable for %s (%s) — falling back to story.md", slug, exc)
        return []
    if not res.ok:
        log.info("ostler set-status failed for %s: %s — falling back to story.md", slug, res.message)
        return []
    return list(res.paths)


def rewrite_status(story_md: Path, new_status: str,
                   logger: logging.Logger | None = None) -> list[Path]:
    """Rewrite (or append) the body's ``- **Status**:`` line. Returns the path written."""
    log = logger or _logger
    text = story_md.read_text(encoding="utf-8")
    if STATUS_LINE_RE.search(text):
        # Rewrite via a temp file + os.replace rather than editing in place, so a
        # write failure can't leave story.md half-written (portable equivalent of
        # the bash original's mktemp+mv, which existed to dodge GNU/BSD `sed -i`
        # incompatibilities entirely).
        new_text = STATUS_LINE_RE.sub(f"- **Status**: {new_status}", text, count=1)
        fd, tmp_name = tempfile.mkstemp(dir=story_md.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(new_text)
            os.replace(tmp_name, story_md)
        except OSError:
            os.unlink(tmp_name)
            log.warning("WARNING: could not rewrite Status in %s", story_md)
            return []
    else:
        with story_md.open("a", encoding="utf-8") as f:
            f.write(f"- **Status**: {new_status}\n")
    return [story_md]


def mark(root: Path, slug: str, new_status: str, *, epic: str = "", story_path: str = "",
         logger: logging.Logger | None = None) -> list[Path]:
    """Stamp ``slug``'s status, graph-first. Returns the paths written (empty if none).

    Never raises: an unstampable status is a degraded run, not a reason to end
    one — the caller's own belt-and-braces (the per-run skip set on the give-up
    path, the epic's commit history on the success path) still applies.
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
