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
    epics = sorted(folder.parent for folder in old_epics.glob("*/epic.md"))
    for epic in epics:
        lines += _move(epic, artifacts / "epics" / epic.name, artifacts if same else None)
    if epics and same:
        lines.append(f"git -C {artifacts} rm -r --cached epics")
    old_adr = artifacts / "adr"
    if old_adr.is_dir():
        for file in sorted(old_adr.glob("*.md")):
            lines += _move(file, home / "docs" / "adrs" / _adr_slug(file) / "adr.md", artifacts if same else None)
    return list(dict.fromkeys(lines))


_QUEUE_ENTRY = re.compile(r"^(\s*-\s*)\[([^\]]+)\]\(([^)]+)/epic\.md\)(.*)$")


def numbered_epics(artifacts: Path) -> list[Path]:
    """The epic folders on the shelf still named ``NNNN-slug``; one directory listing."""
    from ostler import registry

    shelf = artifacts / "epics"
    if not shelf.is_dir():
        return []
    return sorted(d for d in shelf.iterdir()
                  if registry.EPIC_DIR_RE.match(d.name) and (d / "epic.md").is_file())


def _frontmatter(document: Path) -> dict:
    return markdown.split(document.read_text(encoding="utf-8")).frontmatter or {}


def _id_of(document: Path) -> str:
    return str(_frontmatter(document).get("id") or "").strip()


def _record_slug(epic_md: Path, slug: str) -> bool:
    """Write ``slug:`` under the epic's ``id:`` when its frontmatter has none; False when it already had one."""
    text = epic_md.read_text(encoding="utf-8")
    if (markdown.split(text).frontmatter or {}).get("slug"):
        return False
    lines = text.splitlines(keepends=True)
    at = next(i for i, line in enumerate(lines[1:], 1) if line.startswith("id:"))
    lines.insert(at + 1, f"slug: {slug}\n")
    epic_md.write_text("".join(lines), encoding="utf-8")
    return True


def _requeue(shelf: Path, renamed: dict[str, str], slugs: dict[str, str]) -> bool:
    """Point every queue entry at the epic's id folder; False when the queue named nothing that moved."""
    from ostler import registry

    index = shelf / "index.md"
    if not index.is_file():
        return False
    changed = False
    out: list[str] = []
    for line in index.read_text(encoding="utf-8").splitlines(keepends=True):
        match = _QUEUE_ENTRY.match(line.rstrip("\n"))
        name = match.group(2) if match else ""
        eid = (renamed.get(name) or slugs.get(registry.epic_slug(name))) if match else None
        if match and eid and eid != name:
            line = f"{match.group(1)}[{eid}]({eid}/epic.md){match.group(4)}\n"
            changed = True
        out.append(line)
    if changed:
        index.write_text("".join(out), encoding="utf-8")
    return changed


def apply(artifacts: Path) -> tuple[list[str], list[str]]:
    """Rename every epic folder and story folder on the shelf to its id, record each epic's slug, and repoint the queue; returns what moved and what could not."""
    from ostler import registry

    shelf = artifacts / "epics"
    done: list[str] = []
    refused: list[str] = []
    renamed: dict[str, str] = {}
    slugs: dict[str, str] = {}
    for folder in _epic_folders(shelf):
        eid = _id_of(folder / "epic.md")
        if not eid:
            refused.append(f"{folder.name}: epic.md has no `id:`, so it has no name to move to")
            continue
        slug = registry.epic_slug(folder.name)
        if _record_slug(folder / "epic.md", slug):
            done.append(f"{folder.name}: recorded slug `{slug}`")
        slugs[_frontmatter(folder / "epic.md").get("slug") or slug] = eid
        for story_md in sorted((folder / "stories").glob("*/story.md")):
            sid = _id_of(story_md)
            target = story_md.parent.with_name(sid) if sid else None
            if target is None:
                refused.append(f"{folder.name}/stories/{story_md.parent.name}: story.md has no `id:`")
            elif target != story_md.parent:
                if target.exists():
                    refused.append(f"{folder.name}/stories/{story_md.parent.name}: {target.name} already exists")
                else:
                    story_md.parent.rename(target)
                    done.append(f"{folder.name}/stories/{story_md.parent.name} -> {sid}")
        if folder.name != eid:
            target = shelf / eid
            if target.exists():
                refused.append(f"{folder.name}: {eid} already exists")
                continue
            folder.rename(target)
            renamed[folder.name] = eid
            done.append(f"{folder.name} -> {eid}")
    if _requeue(shelf, renamed, slugs):
        done.append("index.md: queue entries now name the id folders")
    return done, refused


def _epic_folders(shelf: Path) -> list[Path]:
    if not shelf.is_dir():
        return []
    return [d for d in sorted(shelf.iterdir()) if (d / "epic.md").is_file()]


def check(artifacts: Path, home: Path) -> None:
    """Raise :class:`LayoutMoveRequired` when *artifacts* holds ``backlog/`` or ``adr/``, *home* holds ``docs/epics/``, or the shelf still names an epic folder ``NNNN-slug``; an emptied folder the moves left behind, or one holding no ``epic.md``, is not a reason to refuse."""
    numbered = numbered_epics(artifacts)
    if numbered:
        names = ", ".join(d.name for d in numbered[:5]) + (", ..." if len(numbered) > 5 else "")
        raise LayoutMoveRequired(
            f"the epics shelf {artifacts / 'epics'} still names {len(numbered)} epic folder(s) by "
            f"number and slug ({names}); epic and story folders are named by their ids now. Run "
            f"`ostler layout apply` to rename them, record each epic's slug and repoint the queue, "
            f"then run ostler again")
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
