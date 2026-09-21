"""Library discovery and the layer resolution stack."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from farrier._vendor.stablemate_core.config import config_path, read_config
from farrier._vendor.stablemate_core.discovery import (
    BASE_DIR_ENV,
    base_library_dir,
    ensure_base_library_dir,
    is_library_dir,
)

__all__ = [
    "BASE_DIR_ENV",
    "BASE_LAYER_NAME",
    "LAYERS",
    "Layer",
    "available_names",
    "base_library_dir",
    "ensure_base_library_dir",
    "find_in_layers",
    "is_library_dir",
    "layer_dirs",
    "resolve_library_dir",
    "searched_layers",
    "set_layers",
]


@dataclass(frozen=True)
class Layer:
    """One library root in the resolution stack."""

    root: Path
    name: str


LAYERS: list[Layer] = []

BASE_LAYER_NAME = "base-library (base)"


def set_layers(overlay: Path | None) -> None:
    """Point the resolution stack at the overlay (if any), then the base (if installed)."""
    layers: list[Layer] = []
    if overlay is not None:
        layers.append(Layer(root=overlay, name=str(overlay)))
    base = base_library_dir()
    if base is not None:
        layers.append(Layer(root=base, name=BASE_LAYER_NAME))
    LAYERS[:] = layers


def layer_dirs(*parts: str) -> list[tuple[Layer, Path]]:
    """(layer, dir) for every layer holding ``<root>/<parts>``, in precedence order."""
    found: list[tuple[Layer, Path]] = []
    for layer in LAYERS:
        candidate = layer.root.joinpath(*parts)
        if candidate.is_dir():
            found.append((layer, candidate))
    return found


def find_in_layers(*parts: str) -> tuple[Layer, Path] | None:
    """The highest-precedence layer holding ``<root>/<parts>``, or None."""
    for layer in LAYERS:
        candidate = layer.root.joinpath(*parts)
        if candidate.exists():
            return layer, candidate
    return None


def searched_layers() -> str:
    """The layer stack, for the 'here is where I looked' half of an error message."""
    if not LAYERS:
        return "  (no library layers — none configured, and no base library installed)"
    return "\n".join(f"  - {layer.name}" for layer in LAYERS)


def available_names(*parts: str, suffix: str = "") -> list[str]:
    """Every name a layer provides under ``<root>/<parts>`` — the catalog for an error's "here is what does exist" half."""
    names: set[str] = set()
    for _layer, directory in layer_dirs(*parts):
        for entry in directory.iterdir():
            if entry.is_file() and (not suffix or entry.name.endswith(suffix)):
                names.add(entry.name[: -len(suffix)] if suffix else entry.name)
    return sorted(names)




def resolve_library_dir(cli_library: Path | None) -> Path | None:
    """Resolve the *overlay* library root: --library > $FARRIER_LIBRARY_DIR > home config."""
    candidate: Path | None = None
    source = ""
    if cli_library is not None:
        candidate, source = cli_library, "--library"
    elif os.environ.get("FARRIER_LIBRARY_DIR"):
        candidate, source = (
            Path(os.environ["FARRIER_LIBRARY_DIR"]),
            "$FARRIER_LIBRARY_DIR",
        )
    else:
        configured = read_config().get("library_dir")
        if configured:
            candidate, source = Path(configured), f"{config_path()}"

    if candidate is None:
        if base_library_dir() is not None:
            return None
        raise SystemExit(
            "error: no library available — no overlay configured, and the base "
            "library could not be fetched.\n"
            "The base is fetched into ~/.cache/stablemate on install; check that git "
            "and the network are reachable, and that $STABLEMATE_FETCH_BASE is not "
            "set to 0.\n"
            "Or point farrier at a base you already have on disk:\n"
            "    farrier config set-base <path-to-base-library>\n"
            "Or at an overlay library:\n"
            "    farrier config set-library <path-to-your-library>\n"
            "(or pass --library DIR / set $FARRIER_LIBRARY_DIR)."
        )

    root = candidate.expanduser().resolve()
    if not is_library_dir(root):
        raise SystemExit(
            f"error: {root} (from {source}) is not a usable library directory "
            "— it must contain library/."
        )
    return root
