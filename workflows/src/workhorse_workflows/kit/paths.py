"""Where the repo is, and where its docs are — from the run's own inputs, not the ambient environment."""
from __future__ import annotations

from pathlib import Path


def find_repo_root(repo_dir: str | Path = "") -> Path:
    """The consuming repo: ``repo_dir`` when given, else walk up from the CWD."""
    if repo_dir:
        return Path(repo_dir).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / ".git").exists():
            return candidate
    return here


def find_docs_root(docs_path: str = "", repo_dir: str | Path = "") -> Path:
    """Resolve the docs repo root: ``docs_path`` when given, else the repo root."""
    if docs_path:
        p = Path(docs_path)
        if p.is_absolute():
            return p.resolve()
        return (find_repo_root(repo_dir) / p).resolve()
    return find_repo_root(repo_dir)
