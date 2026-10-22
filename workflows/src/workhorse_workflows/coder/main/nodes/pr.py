"""The PR boundary: one PR per repo the run branch changed, left open for review; a repo with no origin merges locally."""
from __future__ import annotations

import logging
from pathlib import Path

from github import GithubException
from ostler import path as okf_path, registry
from workhorse_workflows.coder.shared import commits
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.branches import epic_of_branch
from workhorse_workflows.coder.shared.schemas.pr import RunPrs
from workhorse_workflows.kit import (
    branch_exists,
    find_docs_root,
    find_open_pr,
    get_repo_config,
    is_ancestor,
    local_branch_exists,
    merge_into,
    origin_url,
    push_branch,
    resolve_github_token,
    resolve_repo,
    resolve_workspace,
)


@blueprint.node
def open_run_prs(
    logger: logging.Logger,
    branch: str = "",
    base_branch: str = "main",
    epic: str = "",
    story_path: str = "",
    story_slug: str = "",
    stories: list[str] | None = None,
    repo_dir: str = "",
    workspace: str = "",
) -> RunPrs:
    """Push the run branch and open its PR in the docs repo and in every code repo it changed."""
    if not branch:
        logger.info("no run branch — nothing to PR")
        return RunPrs()

    docs_root = find_docs_root(repo_dir)
    repos = resolve_workspace(workspace, repo_dir)
    description = _run_description(docs_root, branch, epic, story_path, story_slug)
    body = _pr_body(stories or [])

    pr_urls: list[str] = []
    for name, path, base in _targets(docs_root, base_branch, repos):
        if not local_branch_exists(path, branch):
            logger.info("%s: no %s, nothing to PR", name, branch)
            continue
        if is_ancestor(path, branch, base):
            logger.info("%s: %s has nothing past %s, nothing to PR", name, branch, base)
            continue
        if not origin_url(path):
            if merge_into(path, branch, base):
                logger.info("%s: no origin remote — merged %s into %s locally", name, branch, base)
            else:
                logger.warning("%s: no origin remote and %s did not merge into %s", name, branch, base)
            continue
        token = resolve_github_token(path)
        if not token:
            logger.info("%s: no GitHub token — leaving %s for a manual PR", name, branch)
            continue
        title = commits.subject("feat", commits.scope(name), description)
        result, url = _push_and_pr(logger, path, branch, base, title, body, token)
        if result != "skipped" and url:
            pr_urls.append(url)

    return RunPrs(status="opened" if pr_urls else "skipped", pr_urls=pr_urls)


def _targets(docs_root: Path, base_branch: str, repos: dict) -> list[tuple[str, Path, str]]:
    """The docs repo against the run's base, then each code repo against its own base."""
    targets = [(docs_root.name, docs_root, base_branch)]
    seen = {docs_root.resolve()}
    for name, info in repos.items():
        path = Path(info.get("path", ""))
        if not (path / ".git").exists() or path.resolve() in seen:
            continue
        seen.add(path.resolve())
        targets.append((name, path, _repo_base_branch(path, name, repos)))
    return targets


def _run_description(root: Path, branch: str, epic: str, story_path: str, story_slug: str) -> str:
    """The PR title's description: the story's title, else the epic's, else the branch name."""
    if story_path and story_slug:
        return commits.story_description(root, story_path, story_slug)
    if epic:
        name = registry.epic_slug(epic) or epic
        try:
            epic_md = okf_path.epic_dir_in(root, epic) / "epic.md"
            return commits.story_description(root, str(epic_md.relative_to(root)), name)
        except (OSError, ValueError, RuntimeError):
            return commits.describe(name)
    return commits.describe(epic_of_branch(branch))


def _pr_body(stories: list[str]) -> str:
    """The PR description: the stories the run delivered, and that the PR waits for review."""
    parts = []
    if stories:
        parts.append("## Stories\n\n" + "\n".join(f"- `{story}`" for story in stories))
    parts.append(
        "---\n*Opened by the coder workflow. It waits for CI to pass and leaves the merge "
        "to a reviewer.*"
    )
    return "\n\n".join(parts)


def _repo_base_branch(repo_path: Path, name: str, repos: dict, fallback: str = "main") -> str:
    """The repo's declared base branch, else the first of develop/main/master it has."""
    declared = get_repo_config(name, "base_branch", repos=repos)
    if declared:
        return declared
    for candidate in ("develop", "main", "master"):
        if branch_exists(repo_path, candidate):
            return candidate
    return fallback


def _push_and_pr(
    logger: logging.Logger,
    repo_path: Path,
    branch: str,
    base: str,
    title: str,
    body: str,
    token: str,
) -> tuple[str, str]:
    """Push one repo's run branch and open its PR: `(opened|exists|skipped, url)`."""
    gh_repo, slug = resolve_repo(repo_path, token)
    if gh_repo is None:
        logger.warning(
            "%s: origin %s not a reachable github.com repo — skipping", repo_path.name, slug
        )
        return "skipped", ""

    if not push_branch(repo_path, token, branch, verify=False):
        logger.warning("push failed for %s in %s", branch, repo_path.name)
        return "skipped", ""

    existing = find_open_pr(gh_repo, branch)
    if existing is not None:
        logger.info("PR already open for %s in %s", branch, repo_path.name)
        return "exists", existing.html_url

    try:
        pr = gh_repo.create_pull(base=base, head=branch, title=title, body=body)
    except GithubException as exc:
        logger.warning("PR create failed in %s: %s", repo_path.name, exc)
        return "skipped", ""

    logger.info("opened PR for %s → %s in %s", branch, base, repo_path.name)
    return "opened", pr.html_url


__all__ = [
    "open_run_prs",
]
