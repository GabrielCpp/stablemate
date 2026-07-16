"""Library discovery and the layer resolution stack.

Where content comes from: locating the base library (env / config / wheel /
checkout), resolving the overlay, and stacking them highest-precedence first so an
overlay shadows the base name-for-name. ``LAYERS`` is mutated in place by
``set_layers`` so every importer of the name sees the current stack.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from farrier.config import CONFIG_PATH, read_config, resolve_stablemate_dir


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
# library shipped as the `stablemate-library` wheel. A higher layer shadows a lower
# one name-for-name, which is how a private overlay overrides a base skill, pack or
# workflow without forking it. Populated by ``set_layers()`` in ``main()``; a module
# global because the rendering helpers below reference it directly.
LAYERS: list[Layer] = []

BASE_LAYER_NAME = "stablemate-library (base)"


# Env var pointing at the base library content on disk. It is the base-layer twin of
# $FARRIER_LIBRARY_DIR (which points at the overlay), and it exists because the
# optional import below only resolves when the `stablemate-library` wheel shares
# farrier's environment. Under pipx — which isolates every app in its own venv —
# `pipx install farrier` cannot import a separately-installed base, so a path handed
# in out-of-band is the only way the two find each other. See docs/LAYOUT.md.
BASE_DIR_ENV = "STABLEMATE_BASE_DIR"


def base_library_dir() -> Path | None:
    """The base library root, or None when it cannot be located.

    Resolution order, highest precedence first:

    1. ``$STABLEMATE_BASE_DIR`` — an explicit on-disk path. This is what makes the
       base reachable when farrier lives in its own isolated environment
       (``pipx install farrier``) and so cannot import the wheel.
    2. The ``base_dir`` key in the home config (``farrier config set-base <path>``) —
       the persisted form of that same override.
    3. An *optional* import of the ``stablemate-library`` wheel — the co-located
       path. ``pip install stablemate-library`` (or
       ``pipx install stablemate-library --include-deps``) puts the wheel in farrier's
       own environment, so ``base_dir()`` just resolves with zero configuration.
    4. Derived from a configured ``stablemate_dir`` checkout
       (``<checkout>/base-library/stablemate_library``) — a convenience for running
       farrier against a source tree.

    Discovery, never a declared dependency: the base package depends on farrier (its
    workflows drive this CLI), so a hard dependency the other way would close a cycle
    and drag every content edit into a farrier release. With none of the above
    resolving, farrier behaves exactly as it did before a base existed: overlay-only.
    A configured-but-invalid override is skipped rather than raised on — the base is
    additive, and failing soft here keeps an overlay-only setup working.
    """
    env = os.environ.get(BASE_DIR_ENV)
    if env:
        candidate = Path(env).expanduser()
        if is_library_dir(candidate):
            return candidate.resolve()

    configured = read_config().get("base_dir")
    if configured:
        candidate = Path(configured).expanduser()
        if is_library_dir(candidate):
            return candidate.resolve()

    try:
        from stablemate_library import base_dir
    except ImportError:
        pass
    else:
        return base_dir()

    checkout = resolve_stablemate_dir()
    if checkout is not None:
        candidate = checkout / "base-library" / "stablemate_library"
        if is_library_dir(candidate):
            return candidate.resolve()

    return None


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


def is_library_dir(path: Path) -> bool:
    """A usable library root holds content: ``library/`` (skills, prompts) or ``workflows/``.

    ``packs/`` is deliberately *not* required. The base library ships workflows,
    scaffolds and the stablemate skills with no packs at all — a repo selects from it
    directly in ``agents.yml`` (``skills: [stablemate/*]``), and packs remain a
    convenience an overlay may add.
    """
    return (path / "library").is_dir() or (path / "workflows").is_dir()


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
            candidate, source = Path(configured), f"{CONFIG_PATH}"

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
