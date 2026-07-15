#!/usr/bin/env python3
"""Resolve the base branch to PR/merge the epic branch against.

Prefers the current branch, falling back to the repo's trunk (origin/HEAD,
else local main, else local master) when HEAD is detached/empty or still
points at a leftover epic branch (feat/* or rewrite/*) from a prior run.

Outputs JSON: {"base_branch": "<branch>"}
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys

from workhorse.scriptutil import find_repo_root

logger = logging.getLogger(__name__)


def _git(args: list[str], root) -> str:
    result = subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


def resolve_trunk(root) -> str:
    default = _git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], root)
    if default.startswith("origin/"):
        default = default[len("origin/"):]
    if default:
        return default
    if _git(["rev-parse", "--verify", "--quiet", "main"], root):
        return "main"
    if _git(["rev-parse", "--verify", "--quiet", "master"], root):
        return "master"
    return "main"


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")
    root = find_repo_root()

    base = _git(["rev-parse", "--abbrev-ref", "HEAD"], root) or "main"
    if base in ("HEAD", ""):
        base = resolve_trunk(root)
    if base.startswith("feat/") or base.startswith("rewrite/"):
        base = resolve_trunk(root)

    print(json.dumps({"base_branch": base}))


if __name__ == "__main__":
    main()
