"""Where the repo is, and where its docs are — from the run's own inputs, not the ambient environment."""
from __future__ import annotations

from pathlib import Path

from ostler import Ostler
from workhorse._vendor.stablemate_core import books, config as core_config


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


def agents_repo_root(repo_dir: str | Path = "") -> Path:
    """*repo_dir* when given, else the nearest ancestor of the cwd holding `agents.yml`, else the cwd; never marked by `.git`. Each answer passes through the docs home, which is the artifacts repo while the repository belongs to a workspace."""
    if repo_dir:
        return docs_home_or(Path(repo_dir).resolve())
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists():
            return docs_home_or(candidate)
    return docs_home_or(here)


def find_book_root(repo_dir: str | Path = "") -> Path:
    """The book root of the repository: the folder `books.book_home` names, the artifacts folder unless the repository's `agents.yml` keeps its book beside the code. It raises `books.UnmovedBook` for a repository that still holds an unmoved book."""
    return books.book_home(find_repo_root(repo_dir))


def find_book_package(repo_dir: str | Path = "") -> str:
    return books.service_package(find_repo_root(repo_dir))


def find_docs_root(repo_dir: str | Path = "") -> Path:
    """The docs root: the artifacts repo while a workspace is active, else the repo root."""
    return docs_home_or(find_repo_root(repo_dir))


def ostler_for(repo_dir: str | Path = "") -> Ostler:
    """The planning facade over the docs root of *repo_dir*, milestones found from its code checkout."""
    return Ostler(agents_repo_root(repo_dir), start=find_repo_root(repo_dir))


def artifacts_root() -> Path:
    """The per-user artifacts folder, where milestones live."""
    return core_config.resolve_artifacts_dir()


def milestone_key(path: str | Path) -> str:
    """The milestone's path relative to the artifacts folder."""
    return Path(path).resolve().relative_to(artifacts_root()).as_posix()
