"""Where the repo is, and where its docs are — from the run's own inputs, not the ambient environment."""
from __future__ import annotations

from pathlib import Path

from workhorse._vendor.stablemate_core import config as core_config


def find_repo_root(repo_dir: str | Path = "") -> Path:
    """The consuming repo: ``repo_dir`` when given, else walk up from the CWD."""
    if repo_dir:
        return Path(repo_dir).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / ".git").exists():
            return candidate
    return here


def docs_home_or(root: Path) -> Path:
    """The artifacts repo while a workspace is active, else ``root``."""
    home = core_config.docs_home(root)
    return home if home is not None else root


def find_docs_root(repo_dir: str | Path = "") -> Path:
    """The docs root: the artifacts repo while a workspace is active, else the repo root."""
    return docs_home_or(find_repo_root(repo_dir))
