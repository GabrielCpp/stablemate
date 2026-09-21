"""Where things are: repo-root resolution, and the derived artifact paths."""
from __future__ import annotations

from pathlib import Path

from ostler import path as okf_path

OPERATOR_DIR = ".agents/operator"

AMBIENT = ("repo_dir", "docs_path", "workspace_file", "library_dirs")


def epics_repo_root(repo_dir: str | Path = "") -> Path:
    """Root marked by `agents.yml` or a `docs/epics/` **directory**, never `.git`."""
    if repo_dir:
        return Path(repo_dir).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / "docs" / "epics").is_dir():
            return candidate
    return here


def launch_repo_root(repo_dir: str | Path = "") -> Path:
    """The operator gates' root: prefer `cwd` when it already looks like one."""
    if repo_dir:
        return Path(repo_dir).resolve()
    cwd = Path.cwd()
    if (cwd / "docs" / "epics").is_dir() or (cwd / "agents.yml").exists() or (cwd / ".git").exists():
        return cwd
    for candidate in cwd.parents:
        if (candidate / "agents.yml").exists() or (candidate / ".git").exists():
            return candidate
    return cwd


def operator_context_path(root: Path, gate: str, epic: str = "") -> Path:
    """The absolute file an `Await` writes its questions into, for `gate` on `epic`."""
    if epic:
        epic_dir = okf_path.epic_dir_in(root, epic)
        if epic_dir.is_dir():
            return epic_dir / f"{gate}-context.md"
        return root / OPERATOR_DIR / f"{gate}-context.{epic}.md"
    return root / OPERATOR_DIR / f"{gate}-context.md"


def _rel(root: Path, target: Path) -> str:
    """*target* as a repo-relative posix string, or absolute if it is outside the repo."""
    try:
        return target.resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return target.as_posix()


def epics_dir(root: Path, configured: str = "") -> str:
    """Where epics live, repo-relative: the run's `epics_dir` parameter, else ostler's."""
    return configured.strip().rstrip("/") or _rel(root, okf_path.epics_root_in(root))


def backlog_file(root: Path, configured: str = "") -> str:
    """The worklist the coder files defects onto, repo-relative."""
    return configured.strip() or _rel(root, okf_path.backlog_path_in(root))


def epic_dir_rel(root: Path, epic: str, configured: str = "") -> str:
    """:func:`epic_dir` as a repo-relative string, honouring an operator's epics root."""
    return _rel(root, okf_path.epic_dir_under(root / epics_dir(root, configured), epic))


def features_dir(root: Path, configured: str = "") -> str:
    """The OKF feature book, repo-relative: what the run was told, else ostler's."""
    return configured.strip().rstrip("/") or _rel(root, okf_path.features_root_in(root))


def epics_index(root: Path) -> str:
    """The epic queue, repo-relative: `index.md` in whichever directory holds the epics."""
    return _rel(root, okf_path.epics_index_in(root))


def epic_dir(root: Path, epic: str) -> Path:
    """The absolute folder of *epic*, by number or by bare slug."""
    return okf_path.epic_dir_in(root, epic)


def story_md(root: Path, epic: str, slug: str) -> Path:
    """The absolute `story.md` of *slug* in *epic*, when nothing else has resolved it."""
    return okf_path.story_dir_in(root, epic, slug) / "story.md"


def story_context_path(story_path: str, repo_dir: str | Path = "") -> Path:
    """The per-story operator context file: `<story-folder>/context.md`."""
    if story_path:
        return Path(story_path).parent / "context.md"
    return launch_repo_root(repo_dir) / "context.md"


def decisions_dir(docs_root: Path) -> Path:
    """Where the operator's standing decisions live: `docs/decisions/` under *docs_root*."""
    return okf_path.backlog_path_in(docs_root).parent / "decisions"


def is_gate_context(path: str | Path) -> bool:
    """Is *path* a file an operator gate wrote, rather than work a story produced?"""
    name = Path(path).name
    if not name.endswith(".md"):
        return False
    stem = name[: -len(".md")]
    return stem == "context" or stem.split(".", 1)[0].endswith("-context")


__all__ = [
    "AMBIENT",
    "OPERATOR_DIR",
    "backlog_file",
    "epic_dir",
    "epic_dir_rel",
    "epics_dir",
    "epics_index",
    "epics_repo_root",
    "features_dir",
    "is_gate_context",
    "launch_repo_root",
    "operator_context_path",
    "story_context_path",
    "story_md",
]
