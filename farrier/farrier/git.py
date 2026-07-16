"""Git repository queries used to seed the launcher scaffolding.

Thin wrappers over ``git`` that fail soft (return None) rather than raise, so a
non-git or remote-less repo still installs.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


def get_git_remote(repo: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return None
    out = result.stdout.strip()
    return out if result.returncode == 0 and out else None


def _git_out(repo: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return None
    out = result.stdout.strip()
    if result.returncode == 0 and out:
        return out
    return None


def get_default_branch(repo: Path) -> str | None:
    """Resolve the repo's DEFAULT (long-lived) branch — master or main — NOT the
    branch currently checked out.

    REPO_BRANCH names the integration branch the worker clones and the coder
    workflow opens PRs against and merges into; it must be the repo's trunk, not
    whatever feature/throwaway branch the installer happened to run from. We probe,
    in order: origin's published default (`origin/HEAD`), then the conventional
    local `main` / `master`, and let the caller fall back to "main".
    """
    # origin's default branch, e.g. "origin/main" → "main".
    head = _git_out(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if head:
        return head.split("/", 1)[-1]
    # No published origin/HEAD — fall back to the conventional trunk names that
    # actually exist (local or on origin).
    for name in ("main", "master"):
        for ref in (f"refs/heads/{name}", f"refs/remotes/origin/{name}"):
            if _git_out(repo, "rev-parse", "--verify", "--quiet", ref) is not None:
                return name
    return None
