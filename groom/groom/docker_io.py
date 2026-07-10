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


def docker_exec(
    container_id: str,
    args: list[str],
    *,
    user: str | None = None,
    env: dict[str, str] | None = None,
    timeout: int = DOCKER_TIMEOUT,
) -> subprocess.CompletedProcess:
    """Run a command inside an already-running container. Far cheaper than a
    throwaway ``docker run`` (no image lookup, no container create/start/teardown)
    and it targets the live container directly — the host→sidecar channel.
    """
    cmd = ["docker", "exec"]
    if user:
        cmd += ["-u", user]
    for key, value in (env or {}).items():
        cmd += ["-e", f"{key}={value}"]
    cmd += [container_id, *args]
    return _run(cmd, timeout=timeout)


def sidecar_query(container_id: str) -> dict[str, Any] | None:
    """Ask a running container's in-container sidecar for its current gate + run
    state in a single call — the fast path that replaces the per-container
    throwaway volume reads (``list_run_dirs`` + ``read_file`` +
    ``grep_awaiting_files``). Invocation mirrors the entrypoint's known-good
    ``gosu nobody env HOME=/claude-state uv run groom-sidecar`` so uv resolves
    the project from the image's ``WORKDIR /app`` exactly as it does at launch.

    Returns the parsed ``{current_node, terminal, gates:[{file_path, question}]}``
    dict, or ``None`` on any failure (container not running, docker/uv error,
    non-JSON output, or a legacy image whose groom-sidecar predates ``--query``)
    so the caller can fall back to the volume-read path.
    """
    try:
        proc = docker_exec(
            container_id,
            ["uv", "run", "groom-sidecar", "--query"],
            user="nobody",
            env={"HOME": "/claude-state"},
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


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


# Vendor/VCS dirs pruned from the gate sweep. A naive `grep -r` over a checkout
# with a full .venv/.git can take tens of seconds (measured ~10s → ~1s once
# pruned); mirrors the sidecar's own _SKIP_DIR_NAMES so both paths agree.
_SKIP_DIRS = (".git", "node_modules", "__pycache__", ".venv")


def grep_awaiting_files(volume: str, mount_subdir: str = "") -> list[str]:
    """Volume-relative paths of every file whose STATUS line reads
    AWAITING_OPERATOR, found via a throwaway read-only container. Prunes heavy
    vendor/VCS dirs with ``find`` (busybox supports ``-prune`` and ``-exec …
    +``) so the sweep stays fast on a real checkout. Shell-free — the volume
    name and target come from trusted docker metadata, but keeping it list-form
    preserves the no-injection invariant. Never raises on a docker failure —
    returns an empty list instead, since this runs during best-effort
    reconciliation, not on a critical path.
    """
    target = f"/vol/{mount_subdir}".rstrip("/") or "/vol"
    prune: list[str] = []
    for i, name in enumerate(_SKIP_DIRS):
        if i:
            prune.append("-o")
        prune += ["-name", name]
    proc = _run(
        [
            "docker", "run", "--rm",
            "-v", f"{volume}:/vol:ro",
            ALPINE_IMAGE,
            "find", target,
            "(", "-type", "d", "(", *prune, ")", "-prune", ")",
            "-o",
            "(", "-type", "f", "-exec",
            "grep", "-lE", "^STATUS:[[:space:]]*AWAITING_OPERATOR", "{}", "+", ")",
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


def list_files(volume: str, repo_dir: str = "") -> list[str]:
    """Repo-relative paths of every file in one checkout inside ``volume`` —
    the tree shown in groom's Files panel. Heavy vendor/VCS dirs are pruned with
    ``find`` (same set as the gate sweep) so a real checkout with a full
    ``.venv``/``.git`` stays fast. ``repo_dir`` is the volume-relative checkout
    dir (from :func:`list_repo_dirs`); "" means the volume root itself is the
    repo. Shell-free; sorted for a stable tree order; ``[]`` on any docker
    failure or an empty repo.
    """
    base = f"/vol/{repo_dir}".rstrip("/") if repo_dir else "/vol"
    prune: list[str] = []
    for i, name in enumerate(_SKIP_DIRS):
        if i:
            prune.append("-o")
        prune += ["-name", name]
    proc = _run(
        [
            "docker", "run", "--rm",
            "-v", f"{volume}:/vol:ro",
            ALPINE_IMAGE,
            "find", base,
            "(", "-type", "d", "(", *prune, ")", "-prune", ")",
            "-o",
            "(", "-type", "f", "-print", ")",
        ],
        timeout=DOCKER_TIMEOUT,
    )
    if proc.returncode != 0:
        return []
    prefix = base + "/"
    files = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith(prefix):
            files.append(line[len(prefix):])
    return sorted(files)


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


def list_repo_dirs(volume: str) -> list[str]:
    """Volume-relative paths of *every* git checkout in a workspace — the
    parent dir of each ``.git`` found within two levels of the volume root.
    Multi-repo workspaces (``.code-workspace`` folders) check several repos
    out side by side under one volume, and each is diffed independently.

    Sorted for a stable UI order; ``[]`` on any docker failure or when the
    volume holds no repos.
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
        return []
    repos = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("/vol/") and line.endswith("/.git"):
            repos.append(line[len("/vol/"):-len("/.git")])
    return sorted(repos)


def find_repo_dir(volume: str) -> str:
    """Volume-relative path to the first git checkout in ``volume`` (see
    :func:`list_repo_dirs`), or ``""`` when there is none. Kept for callers
    that only care about a single repo.
    """
    repos = list_repo_dirs(volume)
    return repos[0] if repos else ""


def git_diff(volume: str, repo_dir: str = "") -> str:
    """Unified working-tree-vs-HEAD diff for one repo inside ``volume``.

    ``repo_dir`` is the volume-relative checkout dir (from
    :func:`list_repo_dirs`); when omitted it defaults to the first repo found,
    preserving the single-repo behaviour. Returns "" on any failure (no repo,
    docker error, git error) — the diff panel is a nice-to-have, not on any
    workflow-critical path.
    """
    repo_dir = repo_dir or find_repo_dir(volume)
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
