"""The ``Source`` record plus loading, selection, and pack resolution."""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from farrier.frontmatter import read_yaml
from farrier.layers import (
    Layer,
    available_names,
    find_in_layers,
    layer_dirs,
)
from farrier.naming import compose_name, kebab, normalize_pattern, source_id
from farrier.selection_errors import unknown_selection_error


@dataclass(frozen=True)
class Source:
    kind: str
    path: Path
    rel: str
    id: str
    layer: Layer | None = None


def library_path(path: Path, fallback: str) -> str:
    """*path* anchored at the last ``library/`` segment, or *fallback*."""
    parts = path.parts
    if "library" in parts:
        idx = len(parts) - 1 - parts[::-1].index("library")
        return Path(*parts[idx:]).as_posix()
    return fallback


def library_source_path(source: Source) -> str:
    """The source's path within the prompt library, for provenance banners."""
    return library_path(source.path, source.rel)


def library_name(source: Source) -> str:
    """The source's folder name: unique across its library, whatever its category."""
    return kebab(Path(source.id).name)


def public_name(prefix: str, source: Source) -> str:
    return compose_name(prefix, library_name(source))


ASSET_DIRS = ("references", "scripts")

_BYPRODUCT_DIRS = frozenset({"__pycache__"})


@dataclass(frozen=True)
class Asset:
    """One file bundled with a skill, to be installed beside its SKILL.md."""

    path: Path
    rel: str

    @property
    def is_script(self) -> bool:
        return self.rel.split("/", 1)[0] == "scripts"


def asset_owner(root: Path, path: Path) -> Path | None:
    """The skill directory owning *path*, or None if *path* is not a bundled asset."""
    rel = path.relative_to(root)
    for index, part in enumerate(rel.parts[:-1]):
        if part in ASSET_DIRS:
            owner = root.joinpath(*rel.parts[:index])
            if (owner / "SKILL.md").is_file():
                return owner
    return None


def skill_assets(source: Source) -> list[Asset]:
    """Every file bundled under *source*'s ``references/``/``scripts/``, sorted."""
    if source.path.name != "SKILL.md":
        return []
    skill_dir = source.path.parent
    assets: list[Asset] = []
    for name in ASSET_DIRS:
        directory = skill_dir / name
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue
            if _BYPRODUCT_DIRS.intersection(path.relative_to(skill_dir).parts):
                continue
            assets.append(Asset(path=path, rel=path.relative_to(skill_dir).as_posix()))
    return sorted(assets, key=lambda asset: asset.rel)


_NOT_SOURCES = frozenset({"SKILL.md", "README.md"})


def load_sources(root: Path, kind: str, layer: Layer | None = None) -> list[Source]:
    sources: list[Source] = []
    for path in sorted(
        list(root.rglob("SKILL.md"))
        + [p for p in root.rglob("*.md") if p.name not in _NOT_SOURCES]
    ):
        if asset_owner(root, path) is not None:
            continue
        rel = path.relative_to(root).as_posix()
        sources.append(
            Source(
                kind=kind, path=path, rel=rel, id=source_id(root, path), layer=layer
            )
        )
    return sources


def layered_sources(kind: str, *parts: str) -> tuple[list[Source], list[tuple[Source, Source]]]:
    """``(sources, overrides)`` across every layer, the higher layer winning by name."""
    by_name: dict[str, Source] = {}
    overrides: list[tuple[Source, Source]] = []
    for layer, root in layer_dirs(*parts):
        in_layer: dict[str, Source] = {}
        for source in load_sources(root, kind, layer):
            name = library_name(source)
            clash = in_layer.get(name)
            if clash is not None:
                raise SystemExit(
                    f"error: two library {kind} sources share the name {name!r}: "
                    f"{clash.rel} and {source.rel} in {layer.name}. A name must be "
                    "unique across its library, whatever folder holds it."
                )
            in_layer[name] = source
            winner = by_name.get(name)
            if winner is None:
                by_name[name] = source
            else:
                overrides.append((winner, source))
    return sorted(by_name.values(), key=lambda source: source.id), overrides


def load_layered_sources(kind: str, *parts: str) -> list[Source]:
    """Sources of one kind across every layer, with the higher layer winning."""
    return layered_sources(kind, *parts)[0]


def override_notices(kind: str, *parts: str) -> list[str]:
    """One info line per library source a higher layer replaces by name."""
    return [
        f"info: {winner.layer.name if winner.layer else winner.rel}: "
        f"{kind} {library_name(winner)!r} ({winner.rel}) overrides "
        f"{loser.layer.name if loser.layer else loser.rel} ({loser.rel})"
        for winner, loser in layered_sources(kind, *parts)[1]
    ]


def parse_scaffold_ids(entries: Any, origin: str) -> set[str]:
    """A `scaffolds` list names scaffold definition ids (see `farrier scaffold`)."""
    ids: set[str] = set()
    for entry in entries or []:
        if not isinstance(entry, str):
            raise SystemExit(
                f"{origin}: scaffolds entries must be scaffold ids (strings); "
                f"got {entry!r}. File-tree scaffolds were replaced by scaffold "
                "definitions — run `farrier scaffold <id> --param key=value` and "
                "list the available ids under `scaffolds:`."
            )
        ids.add(entry)
    return ids


def load_pack(pack_id: str, seen: set[str] | None = None) -> dict[str, Any]:
    seen = seen or set()
    if pack_id in seen:
        raise SystemExit(f"Pack include cycle detected at {pack_id}")
    seen.add(pack_id)

    hit = find_in_layers("packs", f"{pack_id}.yml")
    if hit is None:
        raise SystemExit(
            unknown_selection_error(
                "packs",
                [pack_id],
                available_names("packs", suffix=".yml"),
                extra=(
                    "A pack may also be reached indirectly through another pack's "
                    "`includes:` — check those too if you did not name this one yourself."
                ),
            )
        )
    _layer, path = hit
    data = read_yaml(path)

    merged: dict[str, Any] = {
        "skills": set(data.get("skills", []) or []),
        "prompts": set(data.get("prompts", []) or []),
        "roots": set(data.get("roots", []) or []),
        "scaffolds": parse_scaffold_ids(data.get("scaffolds"), f"pack {pack_id}"),
    }
    for include in data.get("includes", []) or []:
        child = load_pack(str(include), seen)
        for key, values in child.items():
            merged[key].update(values)
    return merged


def collect_selection(
    config: dict[str, Any],
) -> tuple[set[str], set[str], set[str], set[str]]:
    selection: dict[str, Any] = {
        "skills": set(),
        "prompts": set(),
        "roots": set(),
        "scaffolds": set(),
    }
    for pack in config.get("packs", []) or []:
        loaded = load_pack(str(pack))
        for key, values in loaded.items():
            selection[key].update(values)

    selection["scaffolds"].update(
        parse_scaffold_ids(config.get("scaffolds"), "agents.yml")
    )
    for key in ["skills", "prompts", "roots"]:
        selection[key].update(config.get(key, []) or [])

    return (
        selection["skills"],
        selection["prompts"],
        selection["roots"],
        selection["scaffolds"],
    )


def matches(source: Source, patterns: set[str]) -> bool:
    candidates = {
        source.id,
        library_name(source),
        source.rel,
        source.rel.removesuffix(".md"),
        source.rel.removesuffix(".prompt.md"),
        source.rel.removesuffix(".instructions.md"),
    }
    for pattern in patterns:
        all_patterns = {pattern, normalize_pattern(pattern)}
        for candidate in candidates:
            if any(fnmatch.fnmatch(candidate.lower(), item) for item in all_patterns):
                return True
    return False


def selected_sources(
    all_sources: list[Source],
    include_patterns: set[str],
    exclude_patterns: set[str],
) -> list[Source]:
    selected = [
        source
        for source in all_sources
        if matches(source, include_patterns) and not matches(source, exclude_patterns)
    ]
    return sorted(selected, key=lambda item: item.id)


_GLOB_CHARS = set("*?[")


def is_glob(pattern: str) -> bool:
    """Whether a selection entry is a filter rather than a named file."""
    return any(char in _GLOB_CHARS for char in pattern)


def unmatched_patterns(
    all_sources: list[Source], include_patterns: set[str]
) -> tuple[list[str], list[str]]:
    """Include entries that selected nothing, split into ``(literals, globs)``."""
    literals: list[str] = []
    globs: list[str] = []
    for pattern in sorted(include_patterns):
        if any(matches(source, {pattern}) for source in all_sources):
            continue
        (globs if is_glob(pattern) else literals).append(pattern)
    return literals, globs


def build_lookup(sources: list[Source]) -> dict[str, Source]:
    """Library name → source. The name is the only key a reference may use."""
    lookup: dict[str, Source] = {}
    for source in sources:
        name = library_name(source)
        existing = lookup.get(name)
        if existing and existing != source:
            raise SystemExit(
                f"Ambiguous library name {name!r}: {existing.rel} and {source.rel}"
            )
        lookup[name] = source
    return lookup


def build_policy_lookup(sources: list[Source]) -> dict[str, Source]:
    """Name → policy source, addressed by **bare basename** with no prefix."""
    lookup: dict[str, Source] = {}
    for source in sources:
        keys = {
            source.id,
            library_name(source),
            source.rel,
            source.rel.removesuffix(".md"),
        }
        for key in keys:
            normalized = key.replace(".", "-")
            existing = lookup.get(normalized)
            if existing and existing != source:
                raise SystemExit(
                    f"Ambiguous policy name {normalized!r}: "
                    f"{existing.rel} and {source.rel}"
                )
            lookup[normalized] = source
    return lookup
