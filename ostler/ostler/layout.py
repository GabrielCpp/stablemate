"""The Layout move — recognising an artifacts dir or docs home in the old layout and naming the moves, never making them."""

from __future__ import annotations

from pathlib import Path

from ostler import markdown
from ostler._vendor.stablemate_core import books, config as core_config

DECISION_NOTE = (
    "Each moved page needs `date:` and `status:` lines in place of its frontmatter, and a page that "
    "explains one element of one service moves to that service's `decisions/` folder."
)


class LayoutMoveRequired(RuntimeError):
    """The artifacts dir or the docs home still holds a folder from the old layout; the message prints the moves."""


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
    return list(dict.fromkeys(lines))


def _decision_repo(document: Path) -> str | None:
    """The repository a decision names; None when *document* has no ostler shape."""
    try:
        repo = (markdown.split(document.read_text(encoding="utf-8")).frontmatter or {}).get("repo")
    except (OSError, ValueError):
        return None
    return str(repo).strip() if repo else None


def kept_home(home: Path) -> Path:
    """The main checkout of the repository holding *home* when *home* is a linked worktree; *home* itself otherwise."""
    identity = core_config.repository_identity(home)
    if identity.main_folder == identity.folder:
        return home
    return identity.main_folder


def _holders(artifacts: Path, home: Path) -> list[tuple[Path, bool]]:
    """Each folder that may hold old-layout documents, *home* first, with whether it is the artifacts dir itself."""
    if home.resolve() == artifacts.resolve():
        return [(artifacts, True)]
    return [(home, False), (artifacts, True)]


def decision_moves(artifacts: Path, home: Path) -> list[str]:
    """The shell commands that move each ``docs/decisions/<slug>/decision.md`` naming a ``repo:`` in *home* and the artifacts dir to ``products/<repo>/<slug>.md`` of the artifacts dir; a taken target moves to ``<slug>-2``, then ``<slug>-3``."""
    lines: list[str] = []
    planned: set[Path] = set()
    for holder, kept in _holders(artifacts, home):
        moved = False
        for document in sorted((holder / "docs" / "decisions").glob("*/decision.md")):
            repo = _decision_repo(document)
            if repo is None:
                continue
            slug = document.parent.name
            folder = artifacts / "products" / repo
            number, target = 1, folder / f"{slug}.md"
            while target.exists() or target in planned:
                number += 1
                target = folder / f"{slug}-{number}.md"
            planned.add(target)
            lines.append(f"mkdir -p {folder}")
            if kept:
                lines.append(f"git -C {holder} mv docs/decisions/{slug}/decision.md {target.relative_to(holder)}")
            else:
                lines.append(f"mv {document} {target}")
            moved = True
        if moved and not kept and (holder / ".git").exists():
            lines.append(f"git -C {holder} rm -r --cached docs/decisions")
    return list(dict.fromkeys(lines))


def milestone_moves(artifacts: Path, home: Path, start: Path | None = None) -> list[str]:
    """The shell commands that bring the milestones *home* and the artifacts dir still hold under ``docs/milestones`` to ``products/<product>/milestones``, a taken number moving to the next free one."""
    from ostler import registry

    mroot = books.milestones_home(start or home, artifacts)
    if mroot is None:
        return []
    lines: list[str] = []
    taken = [d.name for d in mroot.iterdir()] if mroot.is_dir() else []
    for holder, kept in _holders(artifacts, home):
        moved = False
        for document in sorted((holder / "docs" / "milestones").glob(f"*/{registry.MILESTONE_FILE}")):
            name = document.parent.name
            if registry.epic_seq(name) is not None and any(registry.epic_seq(t) == registry.epic_seq(name) for t in taken):
                name = registry.epic_dir_name(registry.next_epic_seq(taken), registry.epic_slug(name))
            elif name in taken:
                name = registry.epic_dir_name(registry.next_epic_seq(taken), name)
            taken.append(name)
            target = mroot / name
            if kept:
                lines += [f"mkdir -p {mroot}", f"git -C {holder} mv docs/milestones/{document.parent.name} {target.relative_to(holder)}"]
            else:
                lines += [f"mkdir -p {mroot}", f"mv {document.parent} {target}"]
            moved = True
        if moved and not kept and (holder / ".git").exists():
            lines.append(f"git -C {holder} rm -r --cached docs/milestones")
    return list(dict.fromkeys(lines))


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


def apply(artifacts: Path) -> tuple[list[str], list[str]]:
    """Rename every epic folder and story folder on the shelf to its id, and record each epic's slug; returns what moved and what could not."""
    from ostler import registry

    shelf = artifacts / "epics"
    done: list[str] = []
    refused: list[str] = []
    for folder in _epic_folders(shelf):
        eid = _id_of(folder / "epic.md")
        if not eid:
            refused.append(f"{folder.name}: epic.md has no `id:`, so it has no name to move to")
            continue
        slug = registry.epic_slug(folder.name)
        if _record_slug(folder / "epic.md", slug):
            done.append(f"{folder.name}: recorded slug `{slug}`")
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
            done.append(f"{folder.name} -> {eid}")
    return done, refused


def _epic_folders(shelf: Path) -> list[Path]:
    if not shelf.is_dir():
        return []
    return [d for d in sorted(shelf.iterdir()) if (d / "epic.md").is_file()]


def check(artifacts: Path, home: Path, start: Path | None = None) -> None:
    """Raise :class:`LayoutMoveRequired` when *artifacts* holds ``backlog/``, *home* holds ``docs/epics/``, *home* or the artifacts dir holds ``docs/decisions/*/decision.md`` naming a ``repo:``, *home* or the artifacts dir holds ``docs/milestones/*/milestone.md``, or the shelf still names an epic folder ``NNNN-slug``; a linked worktree is judged by its main checkout; an emptied folder the moves left behind, or one holding no ``epic.md``, is not a reason to refuse."""
    numbered = numbered_epics(artifacts)
    if numbered:
        names = ", ".join(d.name for d in numbered[:5]) + (", ..." if len(numbered) > 5 else "")
        raise LayoutMoveRequired(
            f"the epics shelf {artifacts / 'epics'} still names {len(numbered)} epic folder(s) by "
            f"number and slug ({names}); epic and story folders are named by their ids now. Run "
            f"`ostler layout apply` to rename them and record each epic's slug, "
            f"then run ostler again")
    kept = kept_home(home)
    decisions = decision_moves(artifacts, kept)
    lines = moves(artifacts, home) + decisions + milestone_moves(artifacts, kept, start or home)
    if not lines:
        return
    commands = "\n".join(f"  {line}" for line in lines)
    message = f"the artifacts dir {artifacts} is in the old layout; run these commands, then run ostler again:\n{commands}"
    if decisions:
        message += f"\n\n{DECISION_NOTE}"
    raise LayoutMoveRequired(message)
