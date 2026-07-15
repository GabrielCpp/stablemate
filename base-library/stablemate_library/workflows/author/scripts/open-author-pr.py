#!/usr/bin/env python3
"""Push the author run's branch and open a PR in the docs repo.

Author-workflow terminal: after final artifact validation passes, this script
opens one PR in the single docs repo the run wrote into (author never touches
code repos). PR delivery is required: any condition that prevents opening or
finding an open PR exits non-zero so the workflow cannot report success.

Args: <base_branch> <author_branch> <mode> <epic> <bullet>
Outputs JSON: {"author_pr": "opened"|"exists", "pr_url": "https://..."}
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from workhorse.scriptutil import find_repo_root

logger = logging.getLogger(__name__)


def resolve_token(scripts_dir: Path) -> str:
    """Resolve the GitHub token via this workflow's own gh-token.py."""
    try:
        result = subprocess.run(
            [sys.executable, str(scripts_dir / "gh-token.py")],
            capture_output=True, text=True, check=False, timeout=10,
        )
        return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def build_title(mode: str, epic: str, bullet: str) -> str:
    if mode == "survey":
        return "Author: survey intake and epic/story backlog authoring"
    if mode == "story" and epic:
        bullet_trimmed = bullet.strip().splitlines()[0][:72] if bullet.strip() else ""
        return f"Author: {epic} — {bullet_trimmed}" if bullet_trimmed else f"Author: {epic}"
    return "Author: epic/story backlog authoring"


def build_body(mode: str) -> str:
    mode_label = "survey mode" if mode == "survey" else "story mode" if mode == "story" else "epic mode"
    parts = [
        "## Summary",
        "",
        "Automated epic/story docs authored by the `author` workflow"
        + f" ({mode_label}).",
        "",
        "---",
        "*Automated author PR. Left open for review — not auto-merged.*",
    ]
    return "\n".join(parts)


def get_base_branch(repo_path: Path, declared: str, fallback: str = "main") -> str:
    if declared:
        return declared
    for candidate in ("develop", "main", "master"):
        r = subprocess.run(
            ["git", "rev-parse", "--verify", candidate],
            cwd=str(repo_path), capture_output=True, check=False, timeout=10,
        )
        if r.returncode == 0:
            return candidate
    return fallback


def github_slug(url: str) -> str:
    """Return owner/repo for a supported GitHub remote URL."""
    if url.startswith("git@github.com:"):
        return url.removeprefix("git@github.com:").removesuffix(".git")
    if url.startswith("ssh://git@github.com/"):
        return url.removeprefix("ssh://git@github.com/").removesuffix(".git")
    if url.startswith("https://github.com/"):
        return url.removeprefix("https://github.com/").removesuffix(".git")
    return ""


def remote_urls(repo_path: Path) -> list[str]:
    """Read origin's push and fetch URLs, preserving order without duplicates."""
    urls: list[str] = []
    for args in (["--push", "origin"], ["origin"]):
        result = subprocess.run(
            ["git", "-c", f"safe.directory={repo_path}", "remote", "get-url", *args],
            cwd=str(repo_path), capture_output=True, text=True, check=False, timeout=10,
        )
        url = result.stdout.strip() if result.returncode == 0 else ""
        if url and url not in urls:
            urls.append(url)
    return urls


def resolve_github_slug(repo_path: Path) -> str:
    """Resolve GitHub even when this checkout was cloned from a local bind mount.

    Container runs clone the host working tree from paths such as
    ``/mnt/repo-src``. In that case the clone's origin is local, but the mounted
    source repository still carries the real GitHub origin.
    """
    origin_urls = remote_urls(repo_path)
    for url in origin_urls:
        slug = github_slug(url)
        if slug:
            return slug

    for url in origin_urls:
        source_url = url.removeprefix("file://") if url.startswith("file://") else url
        source_path = Path(source_url)
        if not source_path.is_absolute():
            source_path = (repo_path / source_path).resolve()
        if not source_path.exists():
            continue
        for source_origin in remote_urls(source_path):
            slug = github_slug(source_origin)
            if slug:
                return slug
    return ""


def fail(message: str) -> None:
    logger.error(message)
    raise SystemExit(1)


def open_pr_url(repo_path: Path, repo_slug: str, branch: str, token: str) -> str:
    env = {**os.environ, "GH_TOKEN": token}
    result = subprocess.run(
        [
            "gh", "pr", "list", "--repo", repo_slug, "--head", branch,
            "--state", "open", "--json", "url", "--jq", ".[0].url",
        ],
        cwd=str(repo_path), capture_output=True, text=True, check=False, env=env,
        timeout=60,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def push_and_pr(repo_path: Path, branch: str, base: str, title: str, body: str, token: str) -> tuple[str, str]:
    """Push branch and open PR. Returns (status, pr_url)."""
    r = subprocess.run(
        ["git", "rev-parse", "--verify", branch], cwd=str(repo_path),
        capture_output=True, check=False, timeout=10,
    )
    if r.returncode != 0:
        fail(f"no branch {branch} in {repo_path}")

    repo_slug = resolve_github_slug(repo_path)
    if not repo_slug:
        origins = ", ".join(remote_urls(repo_path)) or "<missing>"
        fail(f"origin does not resolve to a github.com repository: {origins}")

    push_url = f"https://github.com/{repo_slug}.git"
    cred_helper = f'!f() {{ echo username=x-access-token; echo "password={token}"; }}; f'

    r = subprocess.run(
        ["git", "-c", f"credential.helper={cred_helper}", "push", push_url, f"{branch}:{branch}"],
        cwd=str(repo_path), capture_output=True, text=True, check=False, timeout=120,
    )
    if r.returncode != 0:
        fail(f"push failed for {branch}: {r.stderr.strip()}")

    pr_url = open_pr_url(repo_path, repo_slug, branch, token)
    if pr_url:
        logger.info("PR already open for %s", branch)
        return "exists", pr_url

    env = {**os.environ, "GH_TOKEN": token}
    r = subprocess.run(
        [
            "gh", "pr", "create", "--repo", repo_slug, "--base", base,
            "--head", branch, "--title", title, "--body", body,
        ],
        cwd=str(repo_path), capture_output=True, text=True, check=False, env=env, timeout=60,
    )
    if r.returncode != 0:
        fail(f"gh pr create failed: {r.stderr.strip()}")

    pr_url = r.stdout.strip() or open_pr_url(repo_path, repo_slug, branch, token)
    if not pr_url:
        fail(f"gh pr create succeeded for {branch}, but no PR URL was returned")
    logger.info("opened PR for %s -> %s", branch, base)
    return "opened", pr_url


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[open-author-pr] %(message)s")

    base_branch = sys.argv[1] if len(sys.argv) > 1 else "main"
    branch = sys.argv[2] if len(sys.argv) > 2 else ""
    mode = sys.argv[3] if len(sys.argv) > 3 else "epic"
    epic = sys.argv[4] if len(sys.argv) > 4 else ""
    bullet = sys.argv[5] if len(sys.argv) > 5 else ""

    if not branch:
        fail("no author branch was provided")

    repo_root = find_repo_root()
    if not (repo_root / ".git").exists():
        fail(f"no .git at {repo_root}")

    scripts_dir = Path(__file__).resolve().parent
    token = resolve_token(scripts_dir)
    if not token:
        fail("no GitHub token is configured; cannot push or open the author PR")

    if shutil.which("gh") is None:
        fail("gh CLI not found; cannot open the author PR")

    base = get_base_branch(repo_root, base_branch)
    title = build_title(mode, epic, bullet)
    body = build_body(mode)

    status, pr_url = push_and_pr(repo_root, branch, base, title, body, token)
    print(json.dumps({"author_pr": status, "pr_url": pr_url}))


if __name__ == "__main__":
    main()
