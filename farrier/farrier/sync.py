"""`farrier sync`: the drift check an agent's commit runs, which repairs what it finds.

A clean tree passes in silence. A drifted one is reinstalled, and the files the install
touched are staged so they ride along with the commit. When the commit names its paths,
staging them would widen it behind the agent's back, so the check lists them and refuses.
"""

from __future__ import annotations

import contextlib
import io
import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

SYNC_BUDGET = 3.0

State = bytes | str | None


def farrier_executable() -> str:
    """The absolute path of the farrier this process runs as."""
    found = shutil.which(sys.argv[0]) or sys.argv[0]
    return str(Path(found).resolve())


def sync_command(repo: Path) -> str:
    """The shell command that runs the drift check for *repo*."""
    return f"{shlex.quote(farrier_executable())} sync --repo {shlex.quote(str(repo))}"


def in_work_tree(repo: Path) -> bool:
    """Whether git sees *repo* as part of a work tree."""
    probe = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--is-inside-work-tree"],
        capture_output=True, text=True, check=False,
    )
    return probe.returncode == 0 and probe.stdout.strip() == "true"


def dirty_paths(repo: Path) -> set[str]:
    """Every path git reports as changed, staged or untracked in *repo*."""
    out = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain", "-z", "--no-renames",
         "--untracked-files=all"],
        capture_output=True, check=True,
    ).stdout.decode("utf-8", errors="surrogateescape")
    return {entry[3:] for entry in out.split("\0") if len(entry) > 3}


def path_state(path: Path) -> State:
    if path.is_symlink():
        return f"symlink to {os.readlink(path)}"
    if path.is_file():
        return path.read_bytes()
    return None


def _snapshot(repo: Path) -> dict[str, State]:
    return {rel: path_state(repo / rel) for rel in dirty_paths(repo)}


def touched_paths(before: dict[str, State], after: dict[str, State]) -> list[str]:
    """Paths whose git status or content differs between two snapshots."""
    return sorted(
        rel for rel in set(before) | set(after)
        if rel not in before or rel not in after or before[rel] != after[rel]
    )


def sync(
    repo: Path,
    pathspecs: list[str],
    check: Callable[[], int],
    install: Callable[[], None],
) -> int:
    """Run *check*, and on drift *install*, then stage or list what the install touched."""
    with contextlib.redirect_stdout(io.StringIO()):
        if check() == 0:
            return 0
    before = _snapshot(repo)
    with contextlib.redirect_stdout(io.StringIO()):
        install()
    touched = touched_paths(before, _snapshot(repo))
    if not touched:
        return 0
    if pathspecs:
        print(
            "Regenerated the drifted agent files. Add these paths to the commit and "
            "commit again:",
            file=sys.stderr,
        )
        for rel in touched:
            print(f"  {rel}", file=sys.stderr)
        return 1
    subprocess.run(["git", "-C", str(repo), "add", "-A", "--", *touched], check=True)
    print(f"Staged {len(touched)} regenerated agent files", file=sys.stderr)
    return 0
