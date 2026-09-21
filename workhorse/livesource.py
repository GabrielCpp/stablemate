"""Installing a package from a read-only bind, without importing the bind itself."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("supervisor.livesource")

COPY_IGNORE = shutil.ignore_patterns(
    ".git", ".venv", "node_modules", "__pycache__", "*.pyc", ".pytest_cache", ".ruff_cache"
)

KEEP_GENERATIONS = 2


@dataclass(frozen=True)
class LiveSource:
    """A package installed from a host bind, one generation at a time."""

    name: str
    mount: Path
    root: Path
    with_editable: tuple[Path, ...] = field(default_factory=tuple)


def generations(root: Path) -> list[Path]:
    """Existing generation dirs, oldest first."""
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and p.name.isdigit())


def stage(source: LiveSource) -> Path | None:
    """Copy the bind into a fresh generation dir and return it."""
    if not source.mount.is_dir():
        return None
    existing = generations(source.root)
    nth = int(existing[-1].name) + 1 if existing else 1
    target = source.root / f"{nth:04d}"
    try:
        source.root.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source.mount, target, ignore=COPY_IGNORE, symlinks=True)
    except OSError as exc:
        log.warning("could not stage %s generation %s: %s", source.name, nth, exc)
        shutil.rmtree(target, ignore_errors=True)
        return None
    return target


def install(source: LiveSource, generation: Path, bin_dir: Path) -> bool:
    """Install one generation as a uv tool, returning whether it worked."""
    cmd = ["uv", "tool", "install", "--force", "--editable", str(generation), "--no-sources"]
    for extra in source.with_editable:
        cmd += ["--with-editable", str(extra)]
    try:
        result = _run(cmd, bin_dir)
    except OSError as exc:
        log.warning("could not install %s: %s", source.name, exc)
        return False
    if result.returncode != 0:
        log.warning(
            "installing %s generation %s failed (exit %d); keeping the previous one",
            source.name, generation.name, result.returncode,
        )
        return False
    return True


def _run(cmd: list[str], bin_dir: Path) -> subprocess.CompletedProcess[bytes]:
    """The one place this module spawns anything — and so the one test seam."""
    return subprocess.run(
        cmd,
        env={**os.environ, "UV_TOOL_BIN_DIR": str(bin_dir)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=False,
    )


def prune(root: Path, keep: int = KEEP_GENERATIONS) -> None:
    """Drop all but the newest `keep` generations."""
    for stale in generations(root)[:-keep] if keep > 0 else generations(root):
        shutil.rmtree(stale, ignore_errors=True)


def refresh(source: LiveSource, bin_dir: Path) -> Path | None:
    """Stage a new generation and install it."""
    generation = stage(source)
    if generation is None:
        return None
    if not install(source, generation, bin_dir):
        shutil.rmtree(generation, ignore_errors=True)
        return None
    log.info("%s: installed generation %s", source.name, generation.name)
    prune(source.root)
    return generation
