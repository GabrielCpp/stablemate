"""The change reads: the uncommitted diff, the diff since the branch started, the files git does not track yet, and whether the read failed."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TypedDict

UNTRACKED_ARGS = ["ls-files", "--others", "--exclude-standard", "-z"]
DIFF_ARGS = ["diff", "HEAD"]
GIT_PREFIX = ["git", "-c", "safe.directory=*", "-c", "diff.autoRefreshIndex=false", "--no-optional-locks"]
VIEW_BRANCH = "branch"
ORIGIN_HEAD = "refs/remotes/origin/HEAD"
ORIGIN_PREFIX = "refs/remotes/origin/"
LOCAL_DEFAULTS = ("main", "master")
REASON_DEFAULT_BRANCH = "default-branch"
REASON_NOT_FOUND = "not-found"


class DiffRead(TypedDict):
    diff: str
    untracked: list[str]
    failed: bool


class BranchStart(TypedDict):
    base: str
    base_ref: str
    base_branch: str
    base_reason: str


class BranchRead(DiffRead, BranchStart):
    pass


def unreadable() -> DiffRead:
    return {"diff": "", "untracked": [], "failed": True}


def parse(diff_rc: int, diff_out: str, untracked_rc: int, untracked_out: str) -> DiffRead:
    """One read from the exit codes and output of its two git commands; either failing fails the read."""
    if diff_rc != 0 or untracked_rc != 0:
        return unreadable()
    return {
        "diff": diff_out,
        "untracked": [path for path in untracked_out.split("\0") if path],
        "failed": False,
    }


class _GitFailed(Exception):
    pass


def _git(root: Path, args: list[str], timeout: float) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            [*GIT_PREFIX, "-C", str(root), *args],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise _GitFailed from exc
    return proc.returncode, proc.stdout


def _read_against(root: Path, diff_args: list[str], timeout: float) -> DiffRead:
    try:
        diff_rc, diff_out = _git(root, diff_args, timeout)
        untracked_rc, untracked_out = _git(root, UNTRACKED_ARGS, timeout)
    except _GitFailed:
        return unreadable()
    return parse(diff_rc, diff_out, untracked_rc, untracked_out)


def read_local(root: Path, timeout: float) -> DiffRead:
    """Read ``root``'s working-tree-vs-HEAD diff and untracked files with the local git."""
    return _read_against(root, DIFF_ARGS, timeout)


def _verified(root: Path, ref: str, timeout: float) -> bool:
    rc, _ = _git(root, ["rev-parse", "--verify", "-q", f"{ref}^{{commit}}"], timeout)
    return rc == 0


def _default_branch(root: Path, timeout: float) -> tuple[str, str] | None:
    """The default branch and the ref it was found at, from local refs only: the ref ``origin/HEAD`` names, else a local ``main``, else a local ``master``."""
    rc, out = _git(root, ["symbolic-ref", "-q", ORIGIN_HEAD], timeout)
    target = out.strip()
    if rc == 0 and target.startswith(ORIGIN_PREFIX) and _verified(root, target, timeout):
        name = target.removeprefix(ORIGIN_PREFIX)
        return name, f"origin/{name}"
    for name in LOCAL_DEFAULTS:
        if _verified(root, f"refs/heads/{name}", timeout):
            return name, name
    return None


def _start(base: str = "", ref: str = "", branch: str = "", reason: str = "") -> BranchStart:
    return {"base": base, "base_ref": ref, "base_branch": branch, "base_reason": reason}


def branch_start(root: Path, timeout: float) -> BranchStart | None:
    """Where the checkout's branch started: the merge base of ``HEAD`` and the default branch, or the reason there is none. ``None`` when git failed."""
    try:
        if not _verified(root, "HEAD", timeout):
            return None
        found = _default_branch(root, timeout)
        if found is None:
            return _start(reason=REASON_NOT_FOUND)
        branch, ref = found
        rc, current = _git(root, ["symbolic-ref", "-q", "--short", "HEAD"], timeout)
        if rc == 0 and current.strip() == branch:
            return _start(ref=ref, branch=branch, reason=REASON_DEFAULT_BRANCH)
        rc, out = _git(root, ["merge-base", "HEAD", ref], timeout)
    except _GitFailed:
        return None
    if rc == 1:
        return _start(ref=ref, branch=branch, reason=REASON_NOT_FOUND)
    if rc != 0 or not out.strip():
        return None
    return _start(base=out.strip(), ref=ref, branch=branch)


def read_branch_local(root: Path, timeout: float) -> BranchRead:
    """Read ``root``'s working-tree diff against the merge base of ``HEAD`` and its default branch, with the untracked files and where the base came from."""
    start = branch_start(root, timeout)
    if start is None:
        return {**unreadable(), **_start()}
    if not start["base"]:
        return {"diff": "", "untracked": [], "failed": False, **start}
    return {**_read_against(root, ["diff", start["base"]], timeout), **start}
