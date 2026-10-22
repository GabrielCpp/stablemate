"""Rebase the relative links of a markdown body from one folder to another."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

from markdown_it import MarkdownIt
from markdown_it.common.utils import unescapeAll
from markdown_it.helpers.parse_link_destination import parseLinkDestination

__all__ = ["rebase_links"]

_MD = MarkdownIt("commonmark")

_BLANKS = " \t\n"


def _masked(segment: str) -> str:
    """*segment* with every code span blanked out, keeping each character's position."""
    out = list(segment)
    i = 0
    size = len(segment)
    while i < size:
        char = segment[i]
        if char == "\\":
            i += 2
            continue
        if char != "`":
            i += 1
            continue
        start = i
        while i < size and segment[i] == "`":
            i += 1
        width = i - start
        j = i
        close = -1
        while j < size:
            if segment[j] != "`":
                j += 1
                continue
            run = j
            while j < size and segment[j] == "`":
                j += 1
            if j - run == width:
                close = j
                break
        if close < 0:
            continue
        for k in range(start, close):
            if out[k] != "\n":
                out[k] = " "
        i = close
    return "".join(out)


def _moved(raw: str, source_dir: Path, target_dir: Path) -> str:
    """The destination *raw* as written beside *source_dir*, rewritten to read from *target_dir*."""
    wrapped = raw.startswith("<") and raw.endswith(">")
    text = raw[1:-1] if wrapped else raw
    cut = min((i for i in (text.find("#"), text.find("?")) if i >= 0), default=len(text))
    path, suffix = text[:cut], text[cut:]
    parts = urlsplit(path)
    if not path or parts.scheme or parts.netloc or path[0] in "/~#":
        return raw
    moved = Path(os.path.relpath(source_dir / path, target_dir)).as_posix()
    if moved == path:
        return raw
    return f"<{moved}{suffix}>" if wrapped else f"{moved}{suffix}"


def _normalized(raw: str) -> str:
    wrapped = raw.startswith("<") and raw.endswith(">")
    return _MD.normalizeLink(unescapeAll(raw[1:-1] if wrapped else raw))


def _destination(segment: str, at: int) -> tuple[int, int] | None:
    """The ``(start, end)`` of the link destination that begins at or after *at*."""
    start = at
    while start < len(segment) and segment[start] in _BLANKS:
        start += 1
    found = parseLinkDestination(segment, start, len(segment))
    if not found.ok or found.pos == start:
        return None
    return start, found.pos


def _rewrite(
    segment: str,
    wanted: list[str],
    opener: str,
    source_dir: Path,
    target_dir: Path,
    masked: str,
) -> str:
    out: list[str] = []
    done = 0
    cursor = 0
    while wanted:
        hit = masked.find(opener, cursor)
        if hit < 0:
            break
        found = _destination(segment, hit + len(opener))
        if found is None:
            cursor = hit + len(opener)
            continue
        start, end = found
        raw = segment[start:end]
        cursor = end
        norm = _normalized(raw)
        if norm not in wanted:
            continue
        wanted.remove(norm)
        out.append(segment[done:start])
        out.append(_moved(raw, source_dir, target_dir))
        done = end
    out.append(segment[done:])
    return "".join(out)


def rebase_links(body: str, source_dir: Path, target_dir: Path) -> str:
    """*body* with each relative link target rewritten from *source_dir* to *target_dir*.

    Inline links, images and reference definitions move. Absolute paths, URLs, `~/`
    paths, pure anchors and anything in code stay as written.
    """
    env: dict = {}
    tokens = _MD.parse(body, env)
    lines = body.split("\n")
    inline: dict[tuple[int, int], list[str]] = {}
    for token in tokens:
        if token.type != "inline" or token.map is None:
            continue
        hrefs = inline.setdefault((token.map[0], token.map[1]), [])
        for child in token.children or []:
            if child.type == "link_open" and child.markup not in ("autolink", "linkify"):
                hrefs.append(str(child.attrGet("href")))
            elif child.type == "image":
                hrefs.append(str(child.attrGet("src")))
    edits: dict[tuple[int, int], str] = {}
    for (first, last), hrefs in inline.items():
        segment = "\n".join(lines[first:last])
        edits[(first, last)] = _rewrite(
            segment, hrefs, "](", source_dir, target_dir, _masked(segment)
        )
    for reference in env.get("references", {}).values():
        first, last = reference["map"]
        segment = "\n".join(lines[first:last])
        edits[(first, last)] = _rewrite(
            segment, [reference["href"]], "]:", source_dir, target_dir, segment
        )
    for (first, last), text in sorted(edits.items(), reverse=True):
        lines[first:last] = text.split("\n")
    return "\n".join(lines)
