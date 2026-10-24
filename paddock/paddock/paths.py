"""Where a benchmark root keeps its benchmarks, and which checkout this package runs from."""

from __future__ import annotations

from pathlib import Path

from paddock._vendor.stablemate_core.config import resolve_paddock_dir

GOLD = "gold"
WORKSPACE = "workspace"
RESULTS = "results"

HOME_CONFIG = "home-config.toml"
TASKS = "tasks.py"
DATA = "data"


def root() -> Path:
    """The benchmark root the home config names."""
    return resolve_paddock_dir()


def gold_dir(root: Path) -> Path:
    return root / GOLD


def benchmark_dir(root: Path, benchmark: str) -> Path:
    return gold_dir(root) / benchmark


def repo_root(start: Path | None = None) -> Path:
    """The nearest ancestor of *start* holding a `.git`, or *start* itself if none does."""
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / ".git").exists():
            return candidate
    return here


def checkout_root() -> Path:
    """The stablemate checkout this package is imported from."""
    return repo_root(Path(__file__).parent)
