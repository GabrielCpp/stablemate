"""The skill reference helpers every stablemate tool renders a template with."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "RETIRED_HELPERS",
    "HarnessFolders",
    "MissingSkill",
    "RetiredHelper",
    "SkillCatalog",
    "SkillEntry",
    "SkillRefs",
    "display_path",
    "harness_folders",
    "repo_root",
    "retired_hint",
    "scan_catalog",
]

SLASH_HARNESSES = frozenset({"claude", "copilot"})
DOLLAR_HARNESSES = frozenset({"codex"})

RETIRED_HELPERS = {
    "instruction_file": "skill_link or skill_path",
    "instruction_ref": "skill_link or skill_path",
    "instruction_refs": "skill_link",
    "skill_file": "skill_path",
    "skill_files": "skill_link",
    "instruction_files": "skill_link",
    "prompt_file": "skill_path",
    "prompt_ref": "skill_path",
    "prompt_refs": "skill_link",
    "prompt_files": "skill_link",
    "skill_dir": "skill_path",
    "skill_load_ref": "skill_command",
    "skill_path_ref": "skill_path",
    "isUsingInstruction": "has_skill",
}


def retired_hint(message: str) -> str:
    """The replacement for a retired helper an undefined-name *message* names, if any."""
    for name, replacement in RETIRED_HELPERS.items():
        if f"'{name}' is undefined" in message:
            return f"\n`{name}` is retired. Call {replacement} with the skill's library name."
    return ""


class RetiredHelper(NameError):
    """A template called a helper that no longer exists."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.helper = name

    def __str__(self) -> str:
        return (
            f"`{self.helper}` is retired. Call {RETIRED_HELPERS[self.helper]} "
            "with the skill's library name."
        )


class MissingSkill(LookupError):
    """A named reference that no catalog entry answers."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name

    def __str__(self) -> str:
        return f"no installed skill or prompt is named {self.name!r}"


@dataclass(frozen=True)
class SkillEntry:
    """One skill or prompt the harness will load, keyed by its library name."""

    name: str
    installed: str
    path: Path
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillCatalog:
    """The entries a render resolves against, the most local first."""

    entries: tuple[SkillEntry, ...] = ()
    _by_name: dict[str, SkillEntry] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        by_name: dict[str, SkillEntry] = {}
        for entry in self.entries:
            by_name.setdefault(entry.name, entry)
        object.__setattr__(self, "_by_name", by_name)

    @classmethod
    def of(cls, entries: Iterable[SkillEntry]) -> SkillCatalog:
        return cls(tuple(entries))

    def get(self, name: str) -> SkillEntry | None:
        return self._by_name.get(name)

    def tagged(self, tags: Iterable[str]) -> list[SkillEntry]:
        """The entries carrying every one of *tags*, by name, each name once."""
        wanted = {tag.lower() for tag in tags}
        if not wanted:
            return []
        return sorted(
            (entry for entry in self._by_name.values() if wanted <= set(entry.tags)),
            key=lambda entry: entry.name,
        )


def display_path(path: Path, *, base: Path, root: Path, home: Path) -> str:
    """*path* relative to *base* when it sits under *root*, else from the home folder."""
    if path.is_relative_to(root):
        return os.path.relpath(path, base).replace(os.sep, "/")
    if path.is_relative_to(home):
        return f"~/{path.relative_to(home).as_posix()}"
    return path.as_posix()


@dataclass(frozen=True)
class SkillRefs:
    """The template helpers for one rendered file, bound to its catalog and harness."""

    catalog: SkillCatalog
    harness: str
    base: Path
    root: Path
    home: Path
    on_missing: Callable[[str], str] | None = None

    def _resolve(self, name: str) -> SkillEntry | str:
        entry = self.catalog.get(name)
        if entry is not None:
            return entry
        if self.on_missing is None:
            raise MissingSkill(name)
        return self.on_missing(name)

    def _show(self, path: Path) -> str:
        return display_path(path, base=self.base, root=self.root, home=self.home)

    def _link(self, entry: SkillEntry) -> str:
        return f"[{entry.installed}]({self._show(entry.path)})"

    def skill_link(self, name: str) -> str:
        found = self._resolve(name)
        return found if isinstance(found, str) else self._link(found)

    def skill_path(self, name: str, relative: str = "") -> str:
        found = self._resolve(name)
        if isinstance(found, str):
            return found
        path = found.path.parent / relative if relative else found.path
        return self._show(path)

    def skill_command(self, name: str) -> str:
        found = self._resolve(name)
        if isinstance(found, str):
            return found
        if self.harness in SLASH_HARNESSES:
            return f"/{found.installed}"
        if self.harness in DOLLAR_HARNESSES:
            return f"${found.installed}"
        return f"Read `{self._show(found.path)}` and follow its instructions"

    def find_by_tags(self, *tags: str) -> str:
        return ", ".join(self._link(entry) for entry in self.catalog.tagged(tags))

    def has_skill(self, name: str) -> bool:
        return self.catalog.get(name) is not None

    def globals(self) -> dict[str, Any]:
        """The helpers by the names a template calls them."""
        return {
            "skill_link": self.skill_link,
            "skill_path": self.skill_path,
            "skill_command": self.skill_command,
            "find_by_tags": self.find_by_tags,
            "has_skill": self.has_skill,
        }


@dataclass(frozen=True)
class HarnessFolders:
    """Where one harness loads skills and prompts from, relative to a folder it searches."""

    skills: tuple[str, ...]
    prompts: tuple[str, ...]
    home_skills: tuple[str, ...]
    home_prompts: tuple[str, ...] = ()
    added_dirs: bool = False


HARNESS_FOLDERS = {
    "claude": HarnessFolders(
        skills=(".claude/skills",),
        prompts=(".claude/commands",),
        home_skills=(".claude/skills",),
        home_prompts=(".claude/commands",),
        added_dirs=True,
    ),
    "codex": HarnessFolders(
        skills=(".agents/skills",),
        prompts=(".agents/prompts",),
        home_skills=(".agents/skills",),
    ),
    "copilot": HarnessFolders(
        skills=(".github/skills", ".agents/skills", ".claude/skills"),
        prompts=(".github/prompts",),
        home_skills=(".agents/skills",),
    ),
}
OTHER_HARNESS = HarnessFolders(
    skills=(".claude/skills", ".agents/skills"),
    prompts=(),
    home_skills=(".claude/skills", ".agents/skills"),
)


def harness_folders(harness: str) -> HarnessFolders:
    return HARNESS_FOLDERS.get(harness, OTHER_HARNESS)


def repo_root(cwd: Path) -> Path:
    """The nearest folder holding `.git` at or above *cwd*, else *cwd* itself."""
    for folder in (cwd, *cwd.parents):
        if (folder / ".git").exists():
            return folder
    return cwd


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _tag_list(value: str, items: list[str]) -> tuple[str, ...]:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    raw = [*value.split(","), *items] if value else items
    return tuple(tag for tag in (_unquote(part).lower() for part in raw) if tag)


def _frontmatter(text: str) -> dict[str, str | tuple[str, ...]]:
    """`name`, `tags` and `metadata.name` / `metadata.tags` from a markdown file's front matter."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    found: dict[str, str | tuple[str, ...]] = {}
    section = ""
    pending: tuple[str, str, list[str]] | None = None

    def flush() -> None:
        if pending is not None:
            key, value, items = pending
            found[key] = _tag_list(value, items)

    for line in lines[1:]:
        if line.strip() == "---":
            break
        stripped = line.strip()
        if pending is not None and stripped.startswith("- "):
            pending[2].append(stripped[2:])
            continue
        flush()
        pending = None
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        nested = line[:1].isspace()
        if not nested:
            section = key if not value.strip() else ""
        scope = f"{section}." if nested and section else ""
        if nested and not section:
            continue
        full = f"{scope}{key.strip()}"
        if key.strip() == "tags":
            pending = (full, value, [])
        else:
            found[full] = _unquote(value)
    flush()
    return found


def _entry(path: Path, installed: str) -> SkillEntry:
    try:
        meta = _frontmatter(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        meta = {}
    own = meta.get("name")
    installed = own if isinstance(own, str) and own else installed
    library = meta.get("metadata.name")
    name = library if isinstance(library, str) and library else installed
    tags = meta.get("metadata.tags", meta.get("tags", ()))
    return SkillEntry(name, installed, path, tags if isinstance(tags, tuple) else ())


def _skills_in(folder: Path) -> list[SkillEntry]:
    if not folder.is_dir():
        return []
    return [
        _entry(skill, skill.parent.name)
        for skill in sorted(folder.glob("*/SKILL.md"))
        if skill.is_file()
    ]


def _prompts_in(folder: Path) -> list[SkillEntry]:
    if not folder.is_dir():
        return []
    return [
        _entry(prompt, prompt.name.removesuffix(".md").removesuffix(".prompt"))
        for prompt in sorted(folder.glob("*.md"))
        if prompt.is_file()
    ]


def scan_catalog(
    harness: str,
    cwd: Path,
    *,
    home: Path,
    added_dirs: Iterable[Path] = (),
    root: Path | None = None,
) -> SkillCatalog:
    """What *harness* loads when started in *cwd*: the cwd up to the repo root, the added dirs, then home."""
    folders = harness_folders(harness)
    top = root if root is not None else repo_root(cwd)
    walk = [cwd, *(parent for parent in cwd.parents if parent.is_relative_to(top))]
    if not cwd.is_relative_to(top):
        walk = [cwd]
    entries: list[SkillEntry] = []
    for folder in walk:
        for rel in folders.skills:
            entries += _skills_in(folder / rel)
        for rel in folders.prompts:
            entries += _prompts_in(folder / rel)
    if folders.added_dirs:
        for added in added_dirs:
            for rel in folders.skills:
                entries += _skills_in(added / rel)
    for rel in folders.home_skills:
        entries += _skills_in(home / rel)
    for rel in folders.home_prompts:
        entries += _prompts_in(home / rel)
    return SkillCatalog.of(entries)
