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
from farrier.layers import Layer, find_in_layers, layer_dirs, searched_layers
from farrier.naming import kebab, normalize_pattern, source_id


@dataclass(frozen=True)
class Source:
    kind: str
    path: Path
    rel: str
    id: str
    # Which library layer this source was read from. None only for sources built
    # outside the layer stack (tests); everything ``load_sources`` produces has one.
    layer: Layer | None = None


def library_source_path(source: Source) -> str:
    """The source's path within the prompt library, for provenance banners.

    Anchored at the last ``library/`` segment so the result is machine-independent
    (e.g. ``library/skills/go/go-qa/SKILL.md``) — identical across machines and
    therefore stable under ``--check``. Falls back to ``source.rel`` if the path is
    not under a ``library/`` tree (it always is for skills/prompts).
    """
    parts = source.path.parts
    if "library" in parts:
        idx = len(parts) - 1 - parts[::-1].index("library")
        return Path(*parts[idx:]).as_posix()
    return source.rel


def public_id(source: Source) -> str:
    return kebab(Path(source.id).name)


def public_name(prefix: str, source: Source) -> str:
    base = public_id(source)
    if base == prefix or base.startswith(f"{prefix}-"):
        return base
    return f"{prefix}-{base}"


def load_sources(root: Path, kind: str, layer: Layer | None = None) -> list[Source]:
    sources: list[Source] = []
    # Load SKILL.md files (new open skill format: <name>/SKILL.md).
    # Also support flat *.md files for backwards compatibility during migration.
    for path in sorted(
        list(root.rglob("SKILL.md"))
        + [p for p in root.rglob("*.md") if p.name != "SKILL.md"]
    ):
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
            f"error: unknown pack: {pack_id}\n"
            f"No library layer provides it. Searched:\n{searched_layers()}\n"
            "If this pack lives in a private overlay library, point farrier at it:\n"
            "    farrier config set-library <path-to-your-library>"
        )
    _layer, path = hit
    data = read_yaml(path)

    merged: dict[str, Any] = {
        "skills": set(data.get("skills", []) or []),
        "prompts": set(data.get("prompts", []) or []),
        "roots": set(data.get("roots", []) or []),
        "scaffolds": parse_scaffold_ids(data.get("scaffolds"), f"pack {pack_id}"),
        "workflows": set(data.get("workflows", []) or []),
    }
    for include in data.get("includes", []) or []:
        child = load_pack(str(include), seen)
        for key, values in child.items():
            merged[key].update(values)
    return merged


def collect_selection(
    config: dict[str, Any],
) -> tuple[set[str], set[str], set[str], set[str], set[str]]:
    selection: dict[str, Any] = {
        "skills": set(),
        "prompts": set(),
        "roots": set(),
        "scaffolds": set(),
        "workflows": set(),
    }
    for pack in config.get("packs", []) or []:
        loaded = load_pack(str(pack))
        for key, values in loaded.items():
            selection[key].update(values)

    selection["scaffolds"].update(
        parse_scaffold_ids(config.get("scaffolds"), "agents.yml")
    )
    for key in ["skills", "prompts", "roots", "workflows"]:
        selection[key].update(config.get(key, []) or [])

    return (
        selection["skills"],
        selection["prompts"],
        selection["roots"],
        selection["scaffolds"],
        selection["workflows"],
    )


def matches(source: Source, patterns: set[str]) -> bool:
    candidates = {
        source.id,
        public_id(source),
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


def build_lookup(sources: list[Source], prefix: str) -> dict[str, Source]:
    lookup: dict[str, Source] = {}
    for source in sources:
        keys = {
            source.id,
            public_id(source),
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
