#!/usr/bin/env python3
"""Merge a finished epic's PR into its base branch, then sync the local
checkout to the merged base so the next epic branches from the right tip.

Args: <epic> [<base_branch>=main]

Outputs JSON: {"merge_status": "merged|unavailable|failed", "base_branch": "<base>"}
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from workhorse.scriptutil import find_repo_root

from lib import ghutil

logger = logging.getLogger(__name__)


def emit(status: str, base: str) -> None:
    print(json.dumps({"merge_status": status, "base_branch": base}))


def sync_base(root, repo_path: str, base: str, env: dict) -> None:
    push_url = f"https://github.com/{repo_path}.git"
    fetch = ghutil.run(
        ["git", "-c", f"credential.helper={ghutil.CRED_HELPER}", "fetch", push_url, base],
        root, env=env, timeout=120, echo=True,
    )
    if fetch.returncode != 0:
        logger.warning("merged but could not fetch '%s' — leaving HEAD as-is; next epic will branch from its tip", base)
        return
    checkout = ghutil.run(["git", "checkout", "-B", base, "FETCH_HEAD"], root, echo=True)
    if checkout.returncode != 0:
        logger.warning("merged but could not check out '%s' — leaving HEAD as-is", base)
        return
    head = ghutil.run(["git", "rev-parse", "--short", "HEAD"], root).stdout.strip()
    logger.info("synced local '%s' to the merged tip (%s)", base, head)


def pick_merge_method(repo_path: str, root, env: dict) -> str:
    result = ghutil.run(
        [
            "gh", "repo", "view", repo_path,
            "--json", "mergeCommitAllowed,squashMergeAllowed,rebaseMergeAllowed",
            "--jq", '"\\(.mergeCommitAllowed) \\(.squashMergeAllowed) \\(.rebaseMergeAllowed)"',
        ],
        root, env=env, timeout=60,
    )
    parts = (result.stdout.split() + ["", "", ""])[:3]
    allow_merge, allow_squash, allow_rebase = parts
    if allow_merge == "true":
        return "merge"
    if allow_squash == "true":
        return "squash"
    if allow_rebase == "true":
        return "rebase"
    return "merge"


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")
    epic = sys.argv[1] if len(sys.argv) > 1 else ""
    base = sys.argv[2] if len(sys.argv) > 2 else "main"
    br = f"feat/{epic}"

    if not epic:
        logger.info("no epic given — nothing to merge")
        emit("unavailable", base)
        return

    root = find_repo_root()
    scripts_dir = Path(__file__).resolve().parent

    token = ghutil.resolve_gh_token(scripts_dir)
    if not token:
        logger.info("no GitHub token (set workflow.githubTokenEnv in agents.yml) — leaving %s unmerged", br)
        emit("unavailable", base)
        return

    if not ghutil.gh_available():
        logger.info("gh CLI not found — leaving %s unmerged", br)
        emit("unavailable", base)
        return

    url = ghutil.origin_url(root)
    if not url:
        logger.info("no 'origin' remote — leaving %s unmerged", br)
        emit("unavailable", base)
        return

    repo_path = ghutil.repo_path_from_url(url)
    if not repo_path:
        logger.info("origin '%s' is not a github.com remote — leaving %s unmerged", url, br)
        emit("unavailable", base)
        return

    env = {**os.environ, "GH_TOKEN": token}

    state = ghutil.run(["gh", "pr", "view", br, "--json", "state", "-q", ".state"], root, env=env, timeout=60).stdout.strip()
    if not state:
        logger.info("no open PR for %s — nothing to merge", br)
        emit("unavailable", base)
        return

    if state == "MERGED":
        logger.info("PR for %s already merged into %s", br, base)
        sync_base(root, repo_path, base, env)
        emit("merged", base)
        return

    method = pick_merge_method(repo_path, root, env)
    logger.info("merging %s into %s with --%s", br, base, method)
    merged = ghutil.run(["gh", "pr", "merge", br, f"--{method}"], root, env=env, timeout=120, echo=True)
    if merged.returncode != 0:
        logger.info(
            "gh pr merge (--%s) failed for %s (merge conflict, branch protection, or not mergeable) — "
            "leaving PR open; next epic will branch from its tip",
            method, br,
        )
        emit("failed", base)
        return

    logger.info("merged %s into %s (--%s)", br, base, method)
    sync_base(root, repo_path, base, env)
    emit("merged", base)


if __name__ == "__main__":
    main()
