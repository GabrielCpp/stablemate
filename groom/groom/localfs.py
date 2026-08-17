"""Local-filesystem reads for **native** runs — the same-host twin of
:mod:`groom.docker_io`.

A native run shares groom's host, so its workspace and run dir are
plain paths groom can read directly: no throwaway container, no volume mount, no
docker at all. These functions mirror the docker_io signatures the dashboard's
Files/Diff/gate handlers already call, but take a **host base path** instead of a
docker volume name, so the handlers branch on ``WorkflowContainer.native`` and call
one or the other with the same shape. That first argument is **positional-only** in
both modules for exactly that reason: each names it after its own concept (a host
base path here, a volume name there), and a handler that picks between them at
runtime must not depend on which name it got.

Path safety is shared with docker_io (``safe_relpath`` rejects traversal); the skip
set (``_SKIP_DIRS``) matches so both paths agree on what a checkout's tree contains.
Every function is best-effort — a bad base path yields an empty result, never a
raise — because a diff/tree panel is a nice-to-have, not on any critical path.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from groom.docker_io import _SKIP_DIRS, DOCKER_TIMEOUT, safe_relpath

_SKIP = set(_SKIP_DIRS)


def _base(base: str, repo_dir: str = "") -> Path | None:
    """The resolved checkout root, or None when it isn't a readable directory —
    which is also groom's test for "is this run native" (its dir exists here)."""
    if not base:
        return None
    root = Path(base)
    if repo_dir:
        root = root / safe_relpath(repo_dir)
    return root if root.is_dir() else None


def is_local_dir(path: str) -> bool:
    """Whether ``path`` is a directory on groom's own host — the signal that a
    telemetry run is native and can be served from local disk."""
    return bool(path) and Path(path).is_dir()


def run_terminal(run_dir: str, /) -> str:
    """The terminal state a native run wrote into its own ``run.json``, or "" while it
    is still in progress (and on any unreadable/missing file).

    This is the run's own account of how it ended, and it is on disk the instant the
    run stops — unlike the root span, which only reaches the collector if the dying
    process got its exporter flushed. That gap is the whole reason to read it: a run
    that died mid-flush is exactly the one an operator most needs to see stop.

    It reports the CURRENT session only. ``--resume-run`` re-writes the record with a
    null terminal before it does anything (``ArtifactWriter.resume``), so a stale
    ending from a previous session cannot make a live resume read as finished.
    """
    if not run_dir:
        return ""
    try:
        record = json.loads((Path(run_dir) / "run.json").read_text())
    except (OSError, ValueError):
        return ""
    return str(record.get("terminal") or "") if isinstance(record, dict) else ""


def pid_alive(pid: int) -> bool:
    """Whether a process with this pid exists on groom's host.

    Only meaningful for a native run, which by definition shares groom's host and
    therefore its pid namespace. Signal 0 checks for existence without delivering
    anything; ``EPERM`` means the process is there and owned by someone else, which
    for this question is a yes.
    """
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
    return True


def list_files(base: str, /, repo_dir: str = "") -> list[str]:
    """Repo-relative paths of every file under one checkout, heavy vendor/VCS dirs
    pruned (same set as the docker path), sorted for a stable tree order."""
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
    """Base-relative paths of every git checkout within two levels of ``base`` —
    the parent dir of each ``.git`` — so a multi-repo workspace diffs each repo."""
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
    """Working-tree-vs-HEAD unified diff for one checkout, run locally (no docker).
    "" on any failure — the diff panel is not on a critical path."""
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
    """Text of one file under ``base``, or None when missing/unreadable. Guarded by
    ``safe_relpath`` so a crafted path can't escape the base."""
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
    """Write ``content`` into a file under ``base`` (the native gate-answer path).
    Returns False on any failure rather than raising."""
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
