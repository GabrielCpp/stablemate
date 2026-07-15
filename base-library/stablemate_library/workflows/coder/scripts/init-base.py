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
import sys

from workhorse.scriptutil import active_branch, branch_exists, default_branch, find_repo_root

logger = logging.getLogger(__name__)


def resolve_trunk(root) -> str:
    trunk = default_branch(root)
    if trunk:
        return trunk
    if branch_exists(root, "main"):
        return "main"
    if branch_exists(root, "master"):
        return "master"
    return "main"


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")
    root = find_repo_root()

    # Prefer the current branch as the PR/merge base; fall back to the repo's trunk
    # when HEAD is detached/empty or still points at a leftover epic branch.
    base = active_branch(root)
    if not base or base.startswith("feat/") or base.startswith("rewrite/"):
        base = resolve_trunk(root)

    print(json.dumps({"base_branch": base}))


if __name__ == "__main__":
    main()
