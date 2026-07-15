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
import subprocess
import sys
from pathlib import Path

from github import Github, GithubException

from workhorse.scriptutil import find_repo_root, get_affected_repos, load_json, resolve_workspace

from lib import ghutil

logger = logging.getLogger(__name__)


def resolve_token(scripts_dir: Path) -> str:
    try:
        result = subprocess.run(
            [sys.executable, str(scripts_dir / "gh-token.py")],
            capture_output=True, text=True, check=False,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def parse_origin_slug(repo_path: Path) -> str:
    """Return 'owner/repo' from the git remote origin URL, or empty string."""
    try:
        r = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, check=False, cwd=str(repo_path),
        )
        if r.returncode != 0:
            return ""
        url = r.stdout.strip()
    except Exception:
        return ""

    if url.startswith("git@github.com:"):
        slug = url.removeprefix("git@github.com:")
    elif url.startswith("ssh://git@github.com/"):
        slug = url.removeprefix("ssh://git@github.com/")
    elif url.startswith("https://github.com/"):
        slug = url.removeprefix("https://github.com/")
    else:
        return ""
    return slug.removesuffix(".git")


def has_commits_ahead(repo_path: Path, branch: str, base: str) -> bool:
    count = ghutil.commits_ahead(branch, base, repo_path)
    return count != 0  # unreachable (-1) counts as "yes"; assume yes and let push decide


def push_branch(repo_path: Path, repo_name: str, branch: str, token: str) -> bool:
    """Push branch via transient credential helper. Returns True on success."""
    origin_slug = parse_origin_slug(repo_path)
    if not origin_slug:
        logger.warning("%s: origin not a github.com URL — skipping push", repo_name)
        return False

    push_url = f"https://github.com/{origin_slug}.git"
    cred_helper = f'!f() {{ echo username=x-access-token; echo "password={token}"; }}; f'
    try:
        r = subprocess.run(
            ["git", "-c", f"credential.helper={cred_helper}", "push", push_url, f"{branch}:{branch}"],
            capture_output=True, text=True, check=False, cwd=str(repo_path), timeout=120,
        )
        if r.returncode != 0:
            logger.warning("%s: push failed: %s", repo_name, r.stderr.strip())
            return False
        return True
    except Exception as exc:
        logger.warning("%s: push error: %s", repo_name, exc)
        return False


def open_or_find_pr(gh_repo, branch: str, base: str, slug: str):
    """Return an open PR for branch (existing or newly created). Returns None on error."""
    owner = gh_repo.owner.login
    try:
        existing = list(gh_repo.get_pulls(head=f"{owner}:{branch}", state="open"))
        if existing:
            logger.info("%s: PR already open for %s", gh_repo.name, branch)
            return existing[0]
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
    scripts_dir = Path(__file__).resolve().parent

    token = resolve_token(scripts_dir)
    if not token:
        logger.info("no GitHub token — leaving %s for manual PRs", branch)
        print(json.dumps({"pr_urls": {}, "opened": "no"}))
        return

    root = find_repo_root()
    repos = resolve_workspace("CODER_WORKSPACE")

    spec_dir_rel = os.environ.get("SPEC_DIR", "")
    plan_ctx = (
        load_json(root / spec_dir_rel / "plan-context.json", "plan-context.json", logger)
        if spec_dir_rel
        else {}
    )
    affected_names = get_affected_repos(plan_ctx, repos)

    # Docs root + affected code repos
    candidates: list[tuple[str, Path]] = [(root.name, root)]
    for name in affected_names:
        repo_path = Path(repos[name]["path"])
        if repo_path != root:
            candidates.append((name, repo_path))

    gh = Github(token)

    # First pass: push + open PR
    pr_records: list[tuple[str, object]] = []  # (repo_name, pr_object)
    pr_urls: dict[str, str] = {}

    for repo_name, repo_path in candidates:
        if not (repo_path / ".git").exists():
            continue

        if not ghutil.local_branch_exists(branch, repo_path):
            logger.info("%s: branch %s not found — skipping", repo_name, branch)
            continue

        if not has_commits_ahead(repo_path, branch, base):
            logger.info("%s: nothing ahead of %s — skipping", repo_name, base)
            continue

        if not push_branch(repo_path, repo_name, branch, token):
            continue

        origin_slug = parse_origin_slug(repo_path)
        if not origin_slug:
            continue

        try:
            gh_repo = gh.get_repo(origin_slug)
        except GithubException as exc:
            logger.warning("%s: cannot access repo %s: %s", repo_name, origin_slug, exc)
            continue

        pr = open_or_find_pr(gh_repo, branch, base, slug)
        if pr is None:
            continue

        pr_urls[repo_name] = pr.html_url
        pr_records.append((repo_name, pr))

    # Second pass: cross-reference comments
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
