"""Where paddock reads its data and where it keeps the bytes."""

from __future__ import annotations

from pathlib import Path

DATA_DIRNAME = "paddock/data"

STORE = Path.home() / ".local" / "share" / "stablemate" / "paddock"


def repo_root(start: Path | None = None) -> Path:
    """The nearest ancestor of *start* holding a `.git`, or *start* itself if none does."""
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / ".git").exists():
            return candidate
    return here


def default_data_dir(start: Path | None = None) -> Path:
    return repo_root(start) / DATA_DIRNAME


def seed_zip(store: Path, name: str) -> Path:
    return store / "seeds" / f"{name}.zip"


def result_zip(store: Path, task: str, label: str) -> Path:
    return store / "results" / task / f"{label}.zip"


def work_dir(store: Path, task: str, label: str) -> Path:
    return store / "work" / task / label


def seed_pointer(data_dir: Path, name: str) -> Path:
    """Where a seed's pointer TOML lives — under `configs/`, with the configs it belongs beside."""
    return data_dir / "configs" / "seeds" / f"{name}.toml"


def result_pointer(data_dir: Path, task: str, label: str) -> Path:
    return data_dir / "results" / task / f"{label}.toml"


def tasks_dir(data_dir: Path) -> Path:
    return data_dir / "tasks"
