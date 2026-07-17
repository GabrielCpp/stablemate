"""Library discovery and the layer resolution stack.

Where content comes from: resolving the overlay and stacking it above the base,
highest-precedence first, so an overlay shadows the base name-for-name. ``LAYERS`` is
mutated in place by ``set_layers`` so every importer of the name sees the current stack.

Locating the *base* is not farrier's business — it is shared with workhorse and lives in
``stablemate_core.discovery``. This module only stacks what that returns.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from stablemate_core.config import config_path, read_config
from stablemate_core.discovery import BASE_DIR_ENV, base_library_dir, is_library_dir

# Re-exported: these moved to stablemate_core, but `farrier.layers` is where the rest of
# farrier (and its tests) has always imported them from. Named in __all__ so ruff does
# not prune them as unused.
__all__ = [
    "BASE_DIR_ENV",
    "BASE_LAYER_NAME",
    "LAYERS",
    "Layer",
    "base_library_dir",
    "find_in_layers",
    "is_library_dir",
    "layer_dirs",
    "resolve_library_dir",
    "searched_layers",
    "set_layers",
]


@dataclass(frozen=True)
class Layer:
    """One library root in the resolution stack.

    ``name`` labels the layer in provenance banners and error messages. Without it,
    an overlay silently shadowing a base skill is invisible — you would open the
    base copy, edit it, and watch the overlay's copy get rendered instead.
    """

    root: Path
    name: str


# Library content resolves across an ordered stack of layers, highest precedence
# first: the overlay (--library / $FARRIER_LIBRARY_DIR / home config), then the base
# library (plain data on disk, or fetched). A higher layer shadows a lower
# one name-for-name, which is how a private overlay overrides a base skill, pack or
# workflow without forking it. Populated by ``set_layers()`` in ``main()``; a module
# global because the rendering helpers below reference it directly.
LAYERS: list[Layer] = []

BASE_LAYER_NAME = "base-library (base)"


def set_layers(overlay: Path | None) -> None:
    """Point the resolution stack at the overlay (if any), then the base (if installed).

    ``LAYERS`` is mutated in place (not rebound) so ``from farrier.layers import
    LAYERS`` bindings in other modules — and the install.py facade — track the
    current stack rather than a stale snapshot.
    """
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




def resolve_library_dir(cli_library: Path | None) -> Path | None:
    """Resolve the *overlay* library root: --library > $FARRIER_LIBRARY_DIR > home config.

    Returns None when no overlay is configured but a base library is installed — the
    base alone is a usable library, so that is a supported setup, not an error. Exits
    with a setup hint only when there is neither an overlay nor a base, or when a
    configured path is not a usable library directory.
    """
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
            "library is not installed.\n"
            "Install the base:\n"
            "    pip install stablemate-library\n"
            "or point farrier at an overlay library:\n"
            "    farrier config set-library <path-to-your-library>\n"
            "(or pass --library DIR / set $FARRIER_LIBRARY_DIR)."
        )

    root = candidate.expanduser().resolve()
    if not is_library_dir(root):
        raise SystemExit(
            f"error: {root} (from {source}) is not a usable library directory "
            "— it must contain library/ or workflows/."
        )
    return root
