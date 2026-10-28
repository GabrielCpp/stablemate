"""Where things are: repo-root resolution, and the derived artifact paths."""
from __future__ import annotations

from pathlib import Path

from ostler import path as okf_path

from workhorse_workflows.kit.paths import docs_home_or


def survey_repo_root(repo_dir: str | Path = "") -> Path:
    """*repo_dir* when given, else the nearest ancestor of the cwd holding `agents.yml`, else the cwd. Each answer passes through the docs home, which is the artifacts repo while the repository belongs to a workspace."""
    if repo_dir:
        return docs_home_or(Path(repo_dir).resolve())
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists():
            return docs_home_or(candidate)
    return docs_home_or(here)


def launch_repo_root(repo_dir: str | Path = "") -> Path:
    """The consuming repo, as the parity surveyor's scripts resolved it: input, else cwd; the artifacts repo while a workspace is active."""
    return docs_home_or(Path(repo_dir).resolve() if repo_dir else Path.cwd().resolve())




def _rel(root: str | Path, target: Path) -> str:
    """*target* as a repo-relative posix string, or absolute if it is outside the repo."""
    root = Path(root)
    try:
        return target.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return target.as_posix()


def epics_dir(root: str | Path) -> str:
    """Where epics live — ostler's answer, `epics/` under the artifacts dir, repo-relative only when the artifacts dir sits inside the repo."""
    return _rel(root, okf_path.epics_root_in(Path(root)))


def services_dir(root: str | Path) -> str:
    """The OKF feature book, repo-relative — the same directory `ostler coverage` reads."""
    return _rel(root, okf_path.services_root_in(Path(root)))


def epic_dir(root: str | Path, epic: str) -> str:
    """Where one epic's artifacts live, repo-relative — ostler resolves the folder."""
    epics_root = Path(root) / epics_dir(root)
    return _rel(root, okf_path.epic_dir_under(epics_root, epic))


def story_dir(epic_dir_rel: str, slug: str) -> str:
    """Where one story's artifacts live, under its epic — `<epic>/stories/<slug>`."""
    return okf_path.story_dir_under(Path(epic_dir_rel), slug).as_posix()


def author_context(root: str | Path) -> str:
    """The run-wide operator context file: the whole-backlog gates write here."""
    return f"{epics_dir(root)}/_author-context.md"


__all__ = [
    "author_context",
    "epic_dir",
    "epics_dir",
    "services_dir",
    "launch_repo_root",
    "story_dir",
    "survey_repo_root",
]
