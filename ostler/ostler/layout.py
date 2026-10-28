"""The Layout move — recognising an artifacts dir or docs home in the old layout and naming the moves, never making them."""

from __future__ import annotations

import re
from pathlib import Path

from ostler import markdown


class LayoutMoveRequired(RuntimeError):
    """The artifacts dir or the docs home still holds a folder from the old layout; the message prints the moves."""


def _slug(text: str) -> str:
    from ostler.decisions import SLUG_MAX

    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")[:SLUG_MAX].strip("-")


def _adr_slug(file: Path) -> str:
    try:
        title = str((markdown.split(file.read_text(encoding="utf-8")).frontmatter or {}).get("title") or "")
    except (OSError, ValueError):
        title = ""
    return _slug(title) or _slug(file.stem) or "decision"


def _move(source: Path, target: Path, repo: Path | None) -> list[str]:
    if repo is None:
        return [f"mkdir -p {target.parent}", f"mv {source} {target}"]
    return [f"mkdir -p {target.parent}", f"git -C {repo} mv {source.relative_to(repo)} {target.relative_to(repo)}"]


def moves(artifacts: Path, home: Path) -> list[str]:
    """The shell commands that bring the old-layout folders under *artifacts* and *home* to the current layout, in order."""
    lines: list[str] = []
    same = home.resolve() == artifacts.resolve()
    if (artifacts / "backlog").is_dir():
        lines += [f"git -C {artifacts} mv backlog backlogs", f"git -C {artifacts} rm -r --cached backlogs"]
    old_epics = home / "docs" / "epics"
    if old_epics.is_dir():
        for epic in sorted(old_epics.iterdir()):
            lines += _move(epic, artifacts / "epics" / epic.name, artifacts if same else None)
        if same:
            lines.append(f"git -C {artifacts} rm -r --cached epics")
    old_adr = artifacts / "adr"
    if old_adr.is_dir():
        for file in sorted(old_adr.glob("*.md")):
            lines += _move(file, home / "docs" / "adrs" / _adr_slug(file) / "adr.md", artifacts if same else None)
    return list(dict.fromkeys(lines))


def check(artifacts: Path, home: Path) -> None:
    """Raise :class:`LayoutMoveRequired` when *artifacts* holds ``backlog/`` or ``adr/``, or *home* holds ``docs/epics/``; three ``stat`` calls when it holds none; an emptied folder the moves left behind is not a reason to refuse."""
    if not (
        (artifacts / "backlog").is_dir()
        or (artifacts / "adr").is_dir()
        or (home / "docs" / "epics").is_dir()
    ):
        return
    lines = moves(artifacts, home)
    if not lines:
        return
    commands = "\n".join(f"  {line}" for line in lines)
    raise LayoutMoveRequired(
        f"the artifacts dir {artifacts} is in the old layout; run these commands, then run ostler again:\n{commands}"
    )
