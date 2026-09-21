"""Stamp a story's Status — the single place the coder workflow records an outcome."""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from ostler import Ostler, markdown, path as okf_path
from ostler.model import status_bullet, story_status

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
    """Set the status through the doc graph."""
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
    """Index of the line carrying the story's Status field, or `None` if it has none."""
    doc = markdown.split(text)
    bullet = status_bullet(doc)
    return doc.body_offset + bullet.line_start if bullet is not None else None


def rewrite_status(
    story_md: Path, new_status: str, logger: logging.Logger | None = None
) -> list[Path]:
    """Rewrite (or append) the body's `- **Status**:` line."""
    log = logger or _logger
    text = story_md.read_text(encoding="utf-8")
    idx = status_line_index(text)
    if idx is not None:
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
    """What the story.md says its status is right now, `""` when it says nothing."""
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
    """Stamp `slug`'s status, graph-first."""
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
