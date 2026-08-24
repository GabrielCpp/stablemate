"""The ``Source`` record plus loading, selection, and pack resolution.

Models one library file, loads them across the layer stack (higher layer wins),
matches them against agents.yml globs, and expands packs into a selection set.
"""
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
    # Which library layer this source was read from. None only for sources built
    # outside the layer stack (tests); everything ``load_sources`` produces has one.
    layer: Layer | None = None


def library_path(path: Path, fallback: str) -> str:
    """*path* anchored at the last ``library/`` segment, or *fallback*.

    Machine-independent by construction (e.g. ``library/skills/go/go-qa/SKILL.md``) —
    identical across machines and therefore stable under ``--check``.
    """
    parts = path.parts
    if "library" in parts:
        idx = len(parts) - 1 - parts[::-1].index("library")
        return Path(*parts[idx:]).as_posix()
    return fallback


def library_source_path(source: Source) -> str:
    """The source's path within the prompt library, for provenance banners.

    Falls back to ``source.rel`` if the path is not under a ``library/`` tree (it
    always is for skills/prompts).
    """
    return library_path(source.path, source.rel)


def public_id(source: Source) -> str:
    """The source's bare basename — its name with neither group nor repo prefix.

    Still the addressable form for a *policy* (``localInstructions`` names one the
    way an author writes it) and one of the aliases selection accepts. It is no
    longer the installed name: see ``group_id``.
    """
    return kebab(Path(source.id).name)


def group_id(source: Source) -> str:
    """``<group>-<basename>`` — the installed name before any repo prefix.

    *group* is the source's **immediate** parent folder, so a nested tree names the
    leaf group and not the path to it: ``stacks/flutter/api`` installs as
    ``flutter-api``, never ``stacks-flutter-api``. A source with no parent folder
    keeps its basename.

    The group is part of the name because user-scope skills carry no repo prefix and
    land in one directory shared by every project on the machine — a bare ``api``
    there says nothing about which stack it belongs to, and collides with the next
    one.
    """
    parts = Path(source.id).parts
    group = kebab(parts[-2]) if len(parts) > 1 else ""
    return compose_name(group, public_id(source))


def public_name(prefix: str, source: Source) -> str:
    return compose_name(prefix, group_id(source))


#: Directories a skill may bundle beside its SKILL.md, shipped with it rather than
#: installed as skills of their own. ``references/`` holds the long-form material a
#: SKILL.md points at instead of inlining (examples, tables, snippets) so the always-
#: loaded body stays short; ``scripts/`` holds the executables a procedure would
#: otherwise ask the agent to retype.
ASSET_DIRS = ("references", "scripts")

#: Byproducts the interpreter leaves in ``scripts/`` and nobody authored. A bundled
#: script is meant to be run, and running one in the library tree writes
#: ``__pycache__/*.pyc`` beside it — binary, so the install pipeline (a ``path -> text``
#: map end to end) refuses it and the generated-file check downgrades itself to a skip
#: on the machine of whoever ran the script. Filtering them out is not leniency about
#: binaries: nothing declared them assets.
_BYPRODUCT_DIRS = frozenset({"__pycache__"})


@dataclass(frozen=True)
class Asset:
    """One file bundled with a skill, to be installed beside its SKILL.md.

    *rel* is the path relative to the owning skill directory (``references/api.md``),
    which is also its path relative to the generated SKILL.md — so a library author
    links a reference with exactly the path they see on disk, in every adapter.
    """

    path: Path
    rel: str

    @property
    def is_script(self) -> bool:
        return self.rel.split("/", 1)[0] == "scripts"


def asset_owner(root: Path, path: Path) -> Path | None:
    """The skill directory owning *path*, or None if *path* is not a bundled asset.

    A directory named ``references``/``scripts`` only means *assets* when it sits
    directly inside a skill — i.e. its parent holds a SKILL.md. Anywhere else it is an
    ordinary library directory that may legitimately contain skills, so the name alone
    must not disqualify it.
    """
    rel = path.relative_to(root)
    # rel.parts[:-1] — the filename itself is never an asset-dir marker.
    for index, part in enumerate(rel.parts[:-1]):
        if part in ASSET_DIRS:
            owner = root.joinpath(*rel.parts[:index])
            if (owner / "SKILL.md").is_file():
                return owner
    return None


def skill_assets(source: Source) -> list[Asset]:
    """Every file bundled under *source*'s ``references/``/``scripts/``, sorted.

    Empty for a flat (non-SKILL.md) source: bundling is a property of the directory
    form, and a flat ``foo.md`` has no directory of its own to bundle into.
    """
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


#: Filenames that never denote a library source of their own: ``SKILL.md`` is the skill
#: it names (loaded by the directory form above), and ``README.md`` is prose for a human
#: reading the tree.
_NOT_SOURCES = frozenset({"SKILL.md", "README.md"})


def load_sources(root: Path, kind: str, layer: Layer | None = None) -> list[Source]:
    sources: list[Source] = []
    # Load SKILL.md files (new open skill format: <name>/SKILL.md).
    # Also support flat *.md files for backwards compatibility during migration.
    #
    # Markdown under a skill's own references/ or scripts/ is skipped: it belongs to
    # that skill and ships beside it (see skill_assets). Without this, splitting a long
    # SKILL.md into references/ would silently register each fragment as a top-level
    # skill of its own — competing for the library-wide-unique names farrier resolves by.
    #
    # A README.md is skipped for the same reason and one more: it is what a human reads
    # to learn what a tree holds, addressed to nobody's agent, and registering it makes a
    # source named `readme` that a pack glob can select and an error catalog advertises.
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


def load_layered_sources(kind: str, *parts: str) -> list[Source]:
    """Sources of one kind across every layer, with the higher layer winning.

    Ids are computed relative to each layer's own content root, so ``stablemate/ostler``
    means the same thing in the overlay and in the base — which is exactly what makes
    shadowing work: an overlay skill with a base skill's id replaces it wholesale.
    """
    by_id: dict[str, Source] = {}
    for layer, root in layer_dirs(*parts):
        for source in load_sources(root, kind, layer):
            # layer_dirs is precedence-ordered, so the first writer of an id wins.
            by_id.setdefault(source.id, source)
    return sorted(by_id.values(), key=lambda source: source.id)


def parse_scaffold_ids(entries: Any, origin: str) -> set[str]:
    """A `scaffolds` list names scaffold definition ids (see `farrier scaffold`).

    Each entry must be a plain string id. The legacy `{source-prefix: dest-dir}`
    mapping form (from the install-time file-tree scaffolds) is rejected with a
    migration hint — placement now comes from scaffold params at invocation time.
    """
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
        public_id(source),
        group_id(source),
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
    """Whether a selection entry is a filter rather than a named file.

    The distinction drives severity: a glob matching nothing is a filter that happened to
    select nothing, which is legitimate. A literal name matching nothing is a **typo** — the
    config promised a specific file that the library does not have.
    """
    return any(char in _GLOB_CHARS for char in pattern)


def unmatched_patterns(
    all_sources: list[Source], include_patterns: set[str]
) -> tuple[list[str], list[str]]:
    """Include entries that selected nothing, split into ``(literals, globs)``.

    Selection is a filter, so an entry naming a file that does not exist contributes nothing
    and the render proceeds — the repo silently ends up without a skill it declared. That
    surfaces much later as an agent running unskilled while every gate still reports success,
    which is the worst shape a failure can take. ``packs`` already fails loudly on the same
    typo (``load_pack``); this closes the gap for skills, prompts, and roots.
    """
    literals: list[str] = []
    globs: list[str] = []
    for pattern in sorted(include_patterns):
        if any(matches(source, {pattern}) for source in all_sources):
            continue
        (globs if is_glob(pattern) else literals).append(pattern)
    return literals, globs


def build_lookup(sources: list[Source], prefix: str) -> dict[str, Source]:
    lookup: dict[str, Source] = {}
    for source in sources:
        keys = {
            source.id,
            public_id(source),
            group_id(source),
            public_name(prefix, source),
            source.rel,
            source.rel.removesuffix(".md"),
            source.rel.removesuffix(".prompt.md"),
        }
        for key in keys:
            normalized = key.replace(".", "-")
            existing = lookup.get(normalized)
            if existing and existing != source:
                raise SystemExit(
                    f"Ambiguous selected source id {normalized!r}: "
                    f"{existing.rel} and {source.rel}"
                )
            lookup[normalized] = source
    return lookup


def build_policy_lookup(sources: list[Source]) -> dict[str, Source]:
    """Name → policy source, addressed by **bare basename** with no prefix.

    Not ``build_lookup``: that one mixes ``public_name(prefix, source)`` into its keys,
    and a policy has no prefix to compose with — ``compose_name("", "stablemate-repo")``
    returns ``"-stablemate-repo"``, so every policy would gain a leading-dash alias and
    the name an author actually writes would be the only one that is not canonical.

    A policy is named the way it is written in ``localInstructions`` — ``stablemate-repo``,
    never ``<repo>-stablemate-repo``. The namespace directory organizes the tree and is
    addressable too (``stablemate/stablemate-repo``), but it is not part of the name; two
    namespaces claiming one basename is an error naming both files, because the reference
    in a repo's config could not say which it meant.
    """
    lookup: dict[str, Source] = {}
    for source in sources:
        keys = {
            source.id,
            public_id(source),
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
