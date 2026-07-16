"""farrier home-config persistence — the TOML file and typed read/write helpers.

One clear capability: where the config lives and how single keys are read and
written, preserving the others. No library-resolution logic lives here (see
``layers``); this module only knows the file.
"""
from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir


# OS-appropriate user config dir (~/.config/farrier on Linux,
# ~/Library/Application Support/farrier on macOS, %APPDATA%\farrier on Windows).
CONFIG_PATH = Path(user_config_dir("farrier")) / "config.toml"


def read_config() -> dict[str, Any]:
    """Read the home config file; return ``{}`` when it does not exist."""
    if not CONFIG_PATH.exists():
        return {}
    with CONFIG_PATH.open("rb") as handle:
        return tomllib.load(handle)


def _write_config_key(key: str, value: str) -> None:
    """Persist a single key to the home config file, preserving other keys."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    cfg = read_config()
    cfg[key] = value
    lines = []
    for k, v in cfg.items():
        escaped = str(v).replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'{k} = "{escaped}"\n')
    CONFIG_PATH.write_text("".join(lines), encoding="utf-8")


def write_library_dir(path: Path) -> None:
    """Persist ``library_dir`` to the home config file."""
    _write_config_key("library_dir", str(path))


def write_stablemate_dir(path: Path) -> None:
    """Persist ``stablemate_dir`` to the home config file."""
    _write_config_key("stablemate_dir", str(path))


def write_base_dir(path: Path) -> None:
    """Persist ``base_dir`` (the base library content path) to the home config file."""
    _write_config_key("base_dir", str(path))


def resolve_stablemate_dir() -> "Path | None":
    """Return the configured stablemate checkout path, or None if unset."""
    configured = read_config().get("stablemate_dir")
    if configured:
        return Path(configured).expanduser().resolve()
    return None
