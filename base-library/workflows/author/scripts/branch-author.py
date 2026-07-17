#!/usr/bin/env python3
"""Cut the working branch for an author run.

Args: <run_dir> [<mode>]

One branch per author run (branch-per-run is the v1 default; branch-per-epic
reuse is a reasonable future upgrade, not needed for a first cut). The branch
name is derived from the run directory's own name (`{workflow}-{run_id}`,
stable for the lifetime of the run — see workhorse's ArtifactWriter), NOT a
fresh timestamp per invocation, so that a script re-run after a mid-run kill
(workhorse's fast-forward/resume logic) checks out the SAME branch instead of
abandoning a partial one. Idempotent: if the branch already exists (a resume),
checks it out WITHOUT resetting it. Records the branch the run started from
as the PR base.

Prints JSON: {"base_branch": "<branch>", "author_branch": "<branch>"}.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from workhorse.scriptutil import active_branch, checkout, find_repo_root, local_branch_exists


def resolve_base_branch(author_branch: str, cwd: Path) -> str:
    current = active_branch(cwd)
    if current and current != author_branch:
        return current

    configured = os.environ.get("REPO_BRANCH", "").strip()
    candidates = [configured, "develop", "main", "master"]
    for candidate in candidates:
        if candidate and candidate != author_branch and local_branch_exists(cwd, candidate):
            return candidate
    return configured or "main"


def derive_run_slug(run_dir: str) -> str:
    if run_dir:
        return Path(run_dir).name
    # No run dir (e.g. manual/local invocation outside workhorse) — fall back to a
    # timestamp so the script still produces a usable branch name.
    return "run-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def main(logger: logging.Logger) -> None:
    run_dir = sys.argv[1] if len(sys.argv) > 1 else ""
    mode = sys.argv[2] if len(sys.argv) > 2 else "epic"

    repo_root = find_repo_root()
    if not (repo_root / ".git").exists():
        logger.info("no .git at %s — skipping branch creation", repo_root)
        print(json.dumps({"base_branch": "main", "author_branch": ""}))
        return

    branch = f"author/{derive_run_slug(run_dir)}"
    base_branch = resolve_base_branch(branch, repo_root)

    if local_branch_exists(repo_root, branch):
        checkout(repo_root, branch)
        logger.info("checked out existing %s", branch)
    else:
        if not checkout(repo_root, branch, create=True):
            logger.warning("cannot create branch %s", branch)
            print(json.dumps({"base_branch": base_branch, "author_branch": ""}))
            return
        logger.info("created %s (mode=%s)", branch, mode)

    print(json.dumps({"base_branch": base_branch, "author_branch": branch}))


if __name__ == "__main__":
    # workhorse calls main(logger) itself; this guard is only for running by hand.
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("branch-author"))
