#!/usr/bin/env python3
"""Merge a finished epic's PR into its base branch, then sync the local
checkout to the merged base so the next epic branches from the right tip.

Args: <epic> [<base_branch>=main]

Outputs JSON: {"merge_status": "merged|unavailable|failed", "base_branch": "<base>"}
"""
from __future__ import annotations

import json
import logging
import sys

from workhorse.scriptutil import (
    find_open_pr,
    find_repo_root,
    origin_url,
    repo_full_name_from_url,
    resolve_github_token,
    resolve_repo,
    sync_to_origin,
)

logger = logging.getLogger(__name__)


def emit(status: str, base: str) -> None:
    print(json.dumps({"merge_status": status, "base_branch": base}))


def sync_base(root, base: str, token: str) -> None:
    head = sync_to_origin(root, token, base)
    if head is None:
        logger.warning(
            "merged but could not sync local '%s' to the merged tip — leaving HEAD "
            "as-is; the next epic will branch from its current tip",
            base,
        )
        return
    logger.info("synced local '%s' to the merged tip (%s)", base, head)


def pick_merge_method(repo) -> str:
    try:
        if repo.allow_merge_commit:
            return "merge"
        if repo.allow_squash_merge:
            return "squash"
        if repo.allow_rebase_merge:
            return "rebase"
    except Exception:
        pass
    return "merge"


def find_merged_pr(repo, branch):
    """Return the most recent MERGED PR for ``branch`` (resume-after-merge case), else None."""
    owner = repo.owner.login
    for pr in repo.get_pulls(state="closed", head=f"{owner}:{branch}"):
        if pr.merged:
            return pr
    return None


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

    token = resolve_github_token(root)
    if not token:
        logger.info("no GitHub token (set workflow.githubTokenEnv in agents.yml) — leaving %s unmerged", br)
        emit("unavailable", base)
        return

    url = origin_url(root)
    if not url:
        logger.info("no 'origin' remote — leaving %s unmerged", br)
        emit("unavailable", base)
        return

    repo_path = repo_full_name_from_url(url)
    if not repo_path:
        logger.info("origin '%s' is not a github.com remote — leaving %s unmerged", url, br)
        emit("unavailable", base)
        return

    repo, _ = resolve_repo(root, token)
    if repo is None:
        logger.info("cannot reach github.com repo %s — leaving %s unmerged", repo_path, br)
        emit("unavailable", base)
        return

    pr = find_open_pr(repo, br)
    if pr is None:
        # No open PR. If one was already merged (e.g. a resume after the merge
        # landed), sync the base and report merged; otherwise nothing to do.
        if find_merged_pr(repo, br) is not None:
            logger.info("PR for %s already merged into %s", br, base)
            sync_base(root, base, token)
            emit("merged", base)
            return
        logger.info("no open PR for %s — nothing to merge", br)
        emit("unavailable", base)
        return

    method = pick_merge_method(repo)
    logger.info("merging %s into %s with --%s", br, base, method)
    try:
        pr.merge(merge_method=method)
    except Exception as exc:
        logger.info(
            "merge (--%s) failed for %s (merge conflict, branch protection, or not mergeable): %s — "
            "leaving PR open; next epic will branch from its tip",
            method, br, exc,
        )
        emit("failed", base)
        return

    logger.info("merged %s into %s (--%s)", br, base, method)
    sync_base(root, base, token)
    emit("merged", base)


if __name__ == "__main__":
    main()
