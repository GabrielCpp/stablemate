"""Where things are: repo-root resolution, and the derived artifact paths."""
from __future__ import annotations

from pathlib import Path

from ostler import path as okf_path


def survey_repo_root(repo_dir: str | Path = "") -> Path:
    """The consuming repo, as the surveyor's scripts resolved it."""
    if repo_dir:
        return Path(repo_dir).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / "docs" / "epics").is_dir():
            return candidate
    return here


def launch_repo_root(repo_dir: str | Path = "") -> Path:
    """The consuming repo, as the parity surveyor's scripts resolved it: input, else cwd."""
    if repo_dir:
        return Path(repo_dir).resolve()
    return Path.cwd().resolve()




def _rel(root: str | Path, target: Path) -> str:
    """*target* as a repo-relative posix string, or absolute if it is outside the repo."""
    root = Path(root)
    try:
        return target.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return target.as_posix()


def epics_dir(root: str | Path) -> str:
    """Where epics live, repo-relative — ostler's answer, read from `docRoots:`."""
    return _rel(root, okf_path.epics_root_in(Path(root)))


def backlog_file(root: str | Path) -> str:
    """The worklist, repo-relative — where ostler keeps it."""
    return _rel(root, okf_path.backlog_path_in(Path(root)))


def roadmaps_dir(root: str | Path) -> str:
    """Where roadmaps live, repo-relative — the location ostler was finally taught."""
    return _rel(root, okf_path.roadmaps_root_in(Path(root)))


def features_dir(root: str | Path) -> str:
    """The OKF feature book, repo-relative — the same directory `ostler coverage` reads."""
    return _rel(root, okf_path.features_root_in(Path(root)))


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


def epic_context(epic_dir_rel: str) -> str:
    """One epic's operator context file: the write-epic, split and coverage gates."""
    return f"{epic_dir_rel.rstrip('/')}/context.md"


def story_context(story_dir_rel: str) -> str:
    """One story's operator context file: the write-story gate."""
    return f"{story_dir_rel.rstrip('/')}/context.md"


__all__ = [
    "author_context",
    "backlog_file",
    "epic_context",
    "epic_dir",
    "epics_dir",
    "features_dir",
    "launch_repo_root",
    "roadmaps_dir",
    "story_context",
    "story_dir",
    "survey_repo_root",
]
