"""What the library holds, and the text of one item — the read side of the layer stack."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from farrier.layers import BASE_LAYER_NAME, LAYERS, Layer, layer_dirs
from farrier.sources import Source, group_id, load_sources

KINDS: dict[str, str] = {
    "skills": "skill",
    "prompts": "prompt",
    "policies": "policy",
    "packs": "pack",
    "scaffolds": "scaffold",
    "roots": "root",
}


@dataclass(frozen=True)
class Item:
    """One addressable library item, and every layer that provides it."""

    name: str
    alias: str
    provided: tuple[tuple[str, Path], ...]

    @property
    def layer(self) -> str:
        """The layer whose copy actually resolves."""
        return self.provided[0][0]

    @property
    def path(self) -> Path:
        """The file that actually resolves."""
        return self.provided[0][1]

    @property
    def shadowed(self) -> tuple[str, ...]:
        """The layers whose copy of this name is hidden by the winner."""
        return tuple(name for name, _ in self.provided[1:])

    def path_in(self, layer: str) -> Path | None:
        for name, path in self.provided:
            if name == layer:
                return path
        return None


def _dirs(*parts: str) -> list[tuple[str, Path]]:
    """``(layer name, dir)`` per layer holding ``<parts>``, one entry per real directory."""
    seen: set[Path] = set()
    found: list[tuple[str, Path]] = []
    for layer, directory in layer_dirs(*parts):
        key = directory.resolve()
        if key in seen:
            continue
        seen.add(key)
        found.append((layer.name, directory))
    return found


def stack() -> list[str]:
    """The layer names the reader is being shown, deduplicated the way :func:`_dirs` is."""
    seen: set[Path] = set()
    names: list[str] = []
    for layer in LAYERS:
        key = layer.root.resolve()
        if key in seen:
            continue
        seen.add(key)
        names.append(layer.name)
    return names


def _layer_name(source: Source) -> str:
    return source.layer.name if source.layer is not None else "?"


def _source_items(kind: str, *parts: str, installed: bool = True) -> list[Item]:
    """Items for a kind loaded as ``Source`` records — skills, prompts, policies."""
    found: dict[str, list[Source]] = {}
    for name, root in _dirs(*parts):
        for source in load_sources(root, kind, Layer(root=root, name=name)):
            found.setdefault(source.id, []).append(source)
    return [
        Item(
            name=name,
            alias=group_id(sources[0]) if installed else "",
            provided=tuple((_layer_name(s), s.path) for s in sources),
        )
        for name, sources in sorted(found.items())
    ]


def _file_items(suffix: str, *parts: str) -> list[Item]:
    """Items for a kind that is one flat file per name — packs, scaffolds, roots."""
    found: dict[str, list[tuple[str, Path]]] = {}
    for name, directory in _dirs(*parts):
        for entry in sorted(directory.iterdir()):
            if entry.is_file() and entry.name.endswith(suffix):
                key = entry.name[: -len(suffix)]
                found.setdefault(key, []).append((name, entry))
    return [
        Item(name=name, alias="", provided=tuple(sources))
        for name, sources in sorted(found.items())
    ]


def items(kind: str) -> list[Item]:
    """Every item of *kind* the resolved stack provides, by name."""
    if kind == "skills":
        return _source_items("skill", "library", "skills")
    if kind == "prompts":
        return _source_items("prompt", "library", "prompts")
    if kind == "policies":
        return _source_items("policy", "library", "policies", installed=False)
    if kind == "packs":
        return _file_items(".yml", "packs")
    if kind == "scaffolds":
        return _file_items(".yml", "scaffolds")
    if kind == "roots":
        return _file_items(".md", "library", "roots")
    raise SystemExit(f"error: unknown library kind {kind!r}")


def layer_label(choice: str) -> str:
    """The stack's real layer name for the shorthand ``base`` / ``overlay``."""
    if choice == "base":
        return BASE_LAYER_NAME
    overlay = [layer.name for layer in LAYERS if layer.name != BASE_LAYER_NAME]
    if not overlay:
        raise SystemExit(
            "error: --layer overlay, but no overlay library is configured — the stack "
            "is the base library alone. Set one with `farrier config set-library <path>`."
        )
    return overlay[0]


def format_list(kinds: list[str], layer: str | None = None) -> str:
    """The catalog, one block per kind, as columns."""
    blocks: list[str] = []
    for kind in kinds:
        found = items(kind)
        if layer is not None:
            found = [item for item in found if item.path_in(layer) is not None]
        blocks.append(_format_kind(kind, found, layer))
    return "\n".join(blocks).rstrip() + "\n"


def _format_kind(kind: str, found: list[Item], layer: str | None) -> str:
    lines = [f"## {kind} ({len(found)})"]
    if not found:
        lines.append("  (none)")
        return "\n".join(lines) + "\n"
    name_width = max(len(item.name) for item in found)
    alias_width = max(len(item.alias) for item in found)
    for item in found:
        columns = [item.name.ljust(name_width)]
        if alias_width:
            columns.append(item.alias.ljust(alias_width))
        if layer is None:
            columns.append(item.layer)
            if item.shadowed:
                columns.append(f"(shadows {', '.join(item.shadowed)})")
        lines.append("  " + "  ".join(columns).rstrip())
    return "\n".join(lines) + "\n"


def find(kind: str, name: str) -> Item:
    """The item of *kind* that *name* addresses — by library id, installed name or basename."""
    catalog = items(kind)
    key = name.replace(".", "-")
    candidates = [
        [item for item in catalog if item.name.replace(".", "-") == key],
        [item for item in catalog if item.alias and item.alias == key],
        [item for item in catalog if item.name.rsplit("/", 1)[-1] == key],
    ]
    for hits in candidates:
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            spellings = "\n".join(f"  - {item.name}" for item in hits)
            raise SystemExit(
                f"error: {name!r} names more than one {KINDS[kind]}:\n{spellings}\n"
                "Address it by its full library id."
            )
    listing = "\n".join(f"  - {item.name}" for item in catalog) or "  (none)"
    raise SystemExit(
        f"error: no {KINDS[kind]} named {name!r}. The stack provides:\n{listing}"
    )
