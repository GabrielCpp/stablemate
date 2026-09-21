"""Local-filesystem reads for **native** runs — the same-host twin of :mod:`groom.docker_io`."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from groom.docker_io import _SKIP_DIRS, DOCKER_TIMEOUT, safe_relpath

_SKIP = set(_SKIP_DIRS)


def _base(base: str, repo_dir: str = "") -> Path | None:
    """The resolved checkout root, or None when it isn't a readable directory — which is also groom's test for "is this run native" (its dir exists here)."""
    if not base:
        return None
    root = Path(base)
    if repo_dir:
        root = root / safe_relpath(repo_dir)
    return root if root.is_dir() else None


def is_local_dir(path: str) -> bool:
    """Whether ``path`` is a directory on groom's own host — the signal that a telemetry run is native and can be served from local disk."""
    return bool(path) and Path(path).is_dir()


def run_terminal(run_dir: str, /) -> str:
    """The terminal state a native run wrote into its own ``run.json``, or "" while it is still in progress (and on any unreadable/missing file)."""
    if not run_dir:
        return ""
    try:
        record = json.loads((Path(run_dir) / "run.json").read_text())
    except (OSError, ValueError):
        return ""
    return str(record.get("terminal") or "") if isinstance(record, dict) else ""


def pid_alive(pid: int) -> bool:
    """Whether a process with this pid exists on groom's host."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return True
    return stat.rpartition(")")[2].split()[0] != "Z"


def list_files(base: str, /, repo_dir: str = "") -> list[str]:
    """Repo-relative paths of every file under one checkout, heavy vendor/VCS dirs pruned (same set as the docker path), sorted for a stable tree order."""
    root = _base(base, repo_dir)
    if root is None:
        return []
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP]
        for name in filenames:
            rel = os.path.relpath(os.path.join(dirpath, name), root)
            out.append(rel.replace(os.sep, "/"))
    return sorted(out)


def list_repo_dirs(base: str, /) -> list[str]:
    """Base-relative paths of every git checkout within two levels of ``base`` — the parent dir of each ``.git`` — so a multi-repo workspace diffs each repo."""
    root = _base(base)
    if root is None:
        return []
    repos: list[str] = []
    if (root / ".git").is_dir():
        repos.append("")
    for child in root.iterdir():
        if child.is_dir() and child.name not in _SKIP and (child / ".git").is_dir():
            repos.append(child.name)
    return sorted(r for r in repos if r != "") or repos


def find_repo_dir(base: str) -> str:
    repos = [r for r in list_repo_dirs(base) if r]
    return repos[0] if repos else ""


def git_diff(base: str, /, repo_dir: str = "") -> str:
    """Working-tree-vs-HEAD unified diff for one checkout, run locally (no docker)."""
    root = _base(base, repo_dir)
    if root is None and not repo_dir:
        repo_dir = find_repo_dir(base)
        root = _base(base, repo_dir)
    if root is None:
        return ""
    try:
        proc = subprocess.run(
            ["git", "-c", "safe.directory=*", "-C", str(root), "diff", "HEAD"],
            capture_output=True,
            text=True,
            timeout=DOCKER_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout if proc.returncode == 0 else ""


def read_file(base: str, /, rel_path: str) -> str | None:
    """Text of one file under ``base``, or None when missing/unreadable."""
    if not base:
        return None
    try:
        rel = safe_relpath(rel_path)
    except ValueError:
        return None
    target = Path(base) / rel
    try:
        return target.read_text()
    except (OSError, ValueError):
        return None


def write_file(base: str, /, rel_path: str, content: str) -> bool:
    """Write ``content`` into a file under ``base`` (the native gate-answer path)."""
    if not base:
        return False
    try:
        rel = safe_relpath(rel_path)
    except ValueError:
        return False
    target = Path(base) / rel
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    except OSError:
        return False
    return True
