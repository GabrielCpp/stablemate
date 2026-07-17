#!/usr/bin/env python3
"""Push story branches and open cross-referenced PRs across all affected repos.

Args: <story_slug> <base_branch>
Outputs JSON: {"pr_urls": {"repo_name": "https://...", ...}, "opened": "yes|no"}

Best-effort: any per-repo failure is logged to stderr and skipped.
Always exits 0 and emits valid JSON.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from github import GithubException

from workhorse.scriptutil import (
    commits_ahead,
    find_open_pr,
    find_repo_root,
    get_affected_repos,
    load_json,
    local_branch_exists,
    push_branch,
    resolve_github_token,
    resolve_repo,
    resolve_workspace,
)

logger = logging.getLogger(__name__)


def open_or_find_pr(gh_repo, branch: str, base: str, slug: str):
    """Return an open PR for branch (existing or newly created). Returns None on error."""
    try:
        existing = find_open_pr(gh_repo, branch)
        if existing is not None:
            logger.info("%s: PR already open for %s", gh_repo.name, branch)
            return existing
        pr = gh_repo.create_pull(
            title=f"story/{slug}",
            body=f"## Story: {slug}\n\nPart of a multi-repo story.",
            head=branch,
            base=base,
        )
        logger.info("%s: opened PR %s", gh_repo.name, pr.html_url)
        return pr
    except GithubException as exc:
        logger.warning("%s: GitHub API error: %s", gh_repo.name, exc)
        return None


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[open-multi-repo-pr] %(message)s")

    slug = sys.argv[1] if len(sys.argv) > 1 else ""
    base = sys.argv[2] if len(sys.argv) > 2 else "main"

    if not slug:
        logger.info("no story slug — nothing to PR")
        print(json.dumps({"pr_urls": {}, "opened": "no"}))
        return

    branch = f"story/{slug}"

    root = find_repo_root()
    token = resolve_github_token(root)
    if not token:
        logger.info("no GitHub token — leaving %s for manual PRs", branch)
        print(json.dumps({"pr_urls": {}, "opened": "no"}))
        return

    repos = resolve_workspace("CODER_WORKSPACE")

    spec_dir_rel = os.environ.get("SPEC_DIR", "")
    plan_ctx = (
        load_json(root / spec_dir_rel / "plan-context.json", "plan-context.json", logger)
        if spec_dir_rel
        else {}
    )
    affected_names = get_affected_repos(plan_ctx, repos)

    # Docs root + affected code repos.
    candidates: list[tuple[str, Path]] = [(root.name, root)]
    for name in affected_names:
        repo_path = Path(repos[name]["path"])
        if repo_path != root:
            candidates.append((name, repo_path))

    # First pass: push + open PR.
    pr_records: list[tuple[str, object]] = []  # (repo_name, pr_object)
    pr_urls: dict[str, str] = {}

    for repo_name, repo_path in candidates:
        if not (repo_path / ".git").exists():
            continue

        if not local_branch_exists(repo_path, branch):
            logger.info("%s: branch %s not found — skipping", repo_name, branch)
            continue

        # commits_ahead returns -1 when the range is unresolvable (e.g. no
        # origin/<base> yet); treat that as "assume yes and let the push decide".
        # Only a definite 0 (nothing ahead) skips the push.
        if commits_ahead(repo_path, branch, base) == 0:
            logger.info("%s: nothing ahead of %s — skipping", repo_name, base)
            continue

        if not push_branch(repo_path, token, branch, verify=False):
            logger.warning("%s: push failed — skipping", repo_name)
            continue

        gh_repo, origin_slug = resolve_repo(repo_path, token)
        if gh_repo is None:
            logger.warning("%s: origin %s not a reachable github.com repo — skipping", repo_name, origin_slug)
            continue

        pr = open_or_find_pr(gh_repo, branch, base, slug)
        if pr is None:
            continue

        pr_urls[repo_name] = pr.html_url
        pr_records.append((repo_name, pr))

    # Second pass: cross-reference comments.
    if len(pr_urls) > 1:
        for repo_name, pr in pr_records:
            siblings = "\n".join(
                f"- {name}: {url}"
                for name, url in pr_urls.items()
                if name != repo_name
            )
            try:
                pr.create_issue_comment(f"**Related PRs:**\n{siblings}")
            except GithubException as exc:
                logger.warning("%s: could not add cross-reference comment: %s", repo_name, exc)

    print(json.dumps({"pr_urls": pr_urls, "opened": "yes" if pr_urls else "no"}))


if __name__ == "__main__":
    main()
