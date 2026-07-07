"""Thin subprocess wrappers around the ``docker`` CLI.

Every call here uses list-form ``subprocess.run`` (no shell), so there is no
shell-injection surface regardless of what a gate's file path or content
contains. ``safe_relpath`` additionally rejects path traversal so a crafted
``file_path`` can't escape the mounted volume root.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

DOCKER_TIMEOUT = 20
ALPINE_IMAGE = "alpine:3.20"
GIT_IMAGE = "alpine/git:2.43.0"


def _run(args: list[str], timeout: int = DOCKER_TIMEOUT, input_text: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, input=input_text)


def docker_ps_all() -> list[dict[str, Any]]:
    proc = _run(["docker", "ps", "-a", "--format", "{{json .}}"])
    if proc.returncode != 0:
        return []
    entries = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def list_container_ids() -> set[str] | None:
    """Short (12-char) IDs of every container that currently exists, or
    ``None`` when the docker CLI call itself failed — so a caller pruning
    stale state can tell "no containers" (prune everything) apart from
    "docker is unreachable" (prune nothing).
    """
    proc = _run(["docker", "ps", "-aq"])
    if proc.returncode != 0:
        return None
    return {line.strip()[:12] for line in proc.stdout.splitlines() if line.strip()}


def docker_inspect(container_id: str) -> dict[str, Any] | None:
    proc = _run(["docker", "inspect", container_id])
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    return data[0] if data else None


def docker_start(container_id: str) -> bool:
    return _run(["docker", "start", container_id], timeout=DOCKER_TIMEOUT).returncode == 0


def is_running(container_id: str) -> bool:
    """True if the container is currently up. Used to skip the now-rare
    ``docker start`` call on the normal path, where the redesigned
    ``await_operator.py`` blocks in place via inotify instead of exiting —
    the container never stopped, so restarting it would be a no-op at best.
    """
    inspect = docker_inspect(container_id)
    if not inspect:
        return False
    return bool(inspect.get("State", {}).get("Running"))


def safe_relpath(path: str) -> str:
    if not path or path.startswith("/") or path.startswith("\\"):
        raise ValueError(f"unsafe path: {path!r}")
    parts = path.replace("\\", "/").split("/")
    if any(part in ("", "..") for part in parts):
        raise ValueError(f"unsafe path: {path!r}")
    return "/".join(parts)


def grep_awaiting_files(volume: str, mount_subdir: str = "") -> list[str]:
    """Volume-relative paths of every file whose STATUS line reads
    AWAITING_OPERATOR, found via a throwaway read-only container. Never
    raises on a docker failure — returns an empty list instead, since this
    runs during best-effort reconciliation, not on a critical path.
    """
    target = f"/vol/{mount_subdir}".rstrip("/") or "/vol"
    proc = _run(
        [
            "docker", "run", "--rm",
            "-v", f"{volume}:/vol:ro",
            ALPINE_IMAGE,
            "grep", "-rlE", "^STATUS:[[:space:]]*AWAITING_OPERATOR", target,
        ],
        timeout=DOCKER_TIMEOUT,
    )
    if proc.returncode not in (0, 1):  # 1 == grep matched nothing; not an error
        return []
    paths = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("/vol/"):
            paths.append(line[len("/vol/"):])
    return paths


def list_run_dirs(volume: str) -> list[str]:
    """Volume-relative top-level directory names under a ``/runs`` volume,
    sorted ascending. Run-id directories embed a sortable timestamp
    (``<workflow>-<YYYYMMDD-HHMMSS>-...``), so the lexicographically last
    entry is also the most recent run.
    """
    proc = _run(
        [
            "docker", "run", "--rm",
            "-v", f"{volume}:/vol:ro",
            ALPINE_IMAGE,
            "find", "/vol", "-mindepth", "1", "-maxdepth", "1", "-type", "d",
        ],
        timeout=DOCKER_TIMEOUT,
    )
    if proc.returncode != 0:
        return []
    dirs = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("/vol/"):
            dirs.append(line[len("/vol/"):])
    return sorted(dirs)


def find_repo_dir(volume: str) -> str:
    """Volume-relative path to the directory containing a git checkout's
    ``.git``, found by searching rather than assumed from ``REPO_NAME`` —
    multi-repo workspaces (``.code-workspace`` folders) can name their
    checkout directories arbitrarily. Empty string if none found within two
    levels of the volume root, or on any docker failure.
    """
    proc = _run(
        [
            "docker", "run", "--rm",
            "-v", f"{volume}:/vol:ro",
            ALPINE_IMAGE,
            "find", "/vol", "-mindepth", "1", "-maxdepth", "2", "-name", ".git", "-type", "d",
        ],
        timeout=DOCKER_TIMEOUT,
    )
    if proc.returncode != 0:
        return ""
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("/vol/") and line.endswith("/.git"):
            return line[len("/vol/"):-len("/.git")]
    return ""


def git_diff(volume: str) -> str:
    """Unified working-tree-vs-HEAD diff for the repo checked out somewhere
    inside ``volume``. Returns "" on any failure (no repo found, docker
    error, git error) — the diff panel is a nice-to-have, not on any
    workflow-critical path.
    """
    repo_dir = find_repo_dir(volume)
    if not repo_dir:
        return ""
    proc = _run(
        [
            "docker", "run", "--rm",
            "-v", f"{volume}:/vol:ro",
            GIT_IMAGE,
            "-c", "safe.directory=*",
            "-C", f"/vol/{repo_dir}",
            "diff", "HEAD",
        ],
        timeout=DOCKER_TIMEOUT,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout


def read_file(volume: str, rel_path: str) -> str | None:
    rel_path = safe_relpath(rel_path)
    proc = _run(
        ["docker", "run", "--rm", "-v", f"{volume}:/vol:ro", ALPINE_IMAGE, "cat", f"/vol/{rel_path}"],
        timeout=DOCKER_TIMEOUT,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout


def write_file(volume: str, rel_path: str, content: str) -> bool:
    """Write ``content`` into a file inside a named volume. Uses ``cp
    /dev/stdin <dest>`` rather than a shell redirect so no shell is ever
    invoked with the (untrusted) content or path in its command line.
    """
    rel_path = safe_relpath(rel_path)
    proc = _run(
        ["docker", "run", "--rm", "-i", "-v", f"{volume}:/vol", ALPINE_IMAGE, "cp", "/dev/stdin", f"/vol/{rel_path}"],
        timeout=DOCKER_TIMEOUT,
        input_text=content,
    )
    return proc.returncode == 0
