"""The CI fix loop's deterministic work: the repo pick, the poll, the push."""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Literal

from github import GithubException
from workhorse_workflows.kit import find_repo_root
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.ci import CiChecks, CiRepoPick, PushOutcome
from workhorse_workflows.kit import (
    branch_exists,
    find_open_pr,
    origin_url,
    push_branch,
    repo_full_name_from_url,
    resolve_github_token,
    resolve_repo,
    resolve_workspace,
)

def epic_branch(epic: str) -> str:
    """The branch an epic's work lives on — the one its PR is opened from."""
    return f"feat/{epic}" if epic else ""


def branch_epic(branch: str) -> str:
    """The epic an epic branch belongs to — `epic_branch` read the other way."""
    return branch.removeprefix("feat/")


FAIL_CONCLUSIONS = frozenset(
    {"failure", "timed_out", "cancelled", "startup_failure", "action_required", "stale"}
)

AUTH_RE = re.compile(
    r"resource not accessible|bad credentials|HTTP 40[13]|requires authentication"
    r"|gh auth login|must authenticate|SAML",
    re.IGNORECASE,
)

NO_RUNS_POLL_LIMIT = 6


@blueprint.node
def select_ci_repo(
    logger: logging.Logger,
    repo: str = "",
    processed: list[str] | None = None,
    workspace_file: str = "",
    launch_dir: str = "",
) -> CiRepoPick:
    """The next repo whose CI has not been looked at yet, or "none left"."""
    seen = list(processed or [])
    repos = resolve_workspace(workspace_file, launch_dir)

    if repo:
        if repo in seen:
            return CiRepoPick(processed=seen)
        if repo not in repos:
            logger.warning("repo '%s' not found in workspace — skipping", repo)
            return CiRepoPick(processed=seen)
        return _picked(repo, repos[repo], seen, launch_dir)

    for name, info in repos.items():
        if name not in seen:
            return _picked(name, info, seen, launch_dir)
    return CiRepoPick(processed=seen)


def _picked(name: str, info: dict, processed: list[str], launch_dir: str = "") -> CiRepoPick:
    """`name` chosen, and appended to the processed list the caller carries onward."""
    return CiRepoPick(
        has_repo=True,
        repo=name,
        repo_cwd=str(info.get("path", find_repo_root(launch_dir))),
        processed=[*processed, name],
    )


@blueprint.node
def poll_pr_checks(
    logger: logging.Logger,
    repo_dir: str,
    branch: str,
    pr_number: str = "",
    watch_timeout: int = 1200,
    poll_interval: int = 30,
) -> CiChecks:
    """Block until the PR's Actions runs settle, then report what they said."""
    if not branch:
        logger.info("no branch given — nothing to gate")
        return CiChecks(status="unavailable", summary="no branch given")

    root = Path(repo_dir) if repo_dir else find_repo_root()
    pr_ref = pr_number or branch

    token = resolve_github_token(root)
    if not token:
        logger.info(
            "no GitHub token (set workflow.githubTokenEnv in agents.yml) — cannot query CI for %s",
            branch,
        )
        return CiChecks(status="unavailable", summary="no GitHub token")
    if not origin_url(root):
        logger.info("no 'origin' remote — cannot query CI for %s", branch)
        return CiChecks(status="unavailable", summary="no origin remote")

    repo, slug = resolve_repo(root, token)
    if repo is None:
        if not slug:
            logger.info("origin is not a github.com repo — cannot query CI for %s", branch)
            return CiChecks(status="unavailable", summary="origin not a github.com remote")
        logger.warning("cannot reach github repo '%s' — CI for %s was never gated", slug, branch)
        return CiChecks(status="blocked", summary=f"github repo {slug} is unreachable")

    pr = _resolve_pr(repo, pr_ref)
    if pr is None:
        logger.info("no open PR for %s — cannot gate on CI", pr_ref)
        return CiChecks(status="unavailable", summary=f"no open PR for {pr_ref}")

    try:
        head_sha = pr.head.sha
    except GithubException:
        head_sha = ""
    if not head_sha:
        logger.warning("could not resolve head SHA for %s — CI was never gated", pr_ref)
        return CiChecks(
            status="blocked", summary=f"could not resolve head SHA for {pr_ref}"
        )

    return _watch(logger, repo, branch, head_sha, watch_timeout, poll_interval)


def _resolve_pr(repo, pr_ref: str):
    """The PR by explicit number, else the open one whose head is that branch."""
    if pr_ref.isdigit():
        try:
            return repo.get_pull(int(pr_ref))
        except GithubException:
            return None
    return find_open_pr(repo, pr_ref)


def _poll_runs(repo, head_sha: str) -> tuple[int, int, int, str]:
    """`(total, pending, failed, failing_names)` for the Actions runs on `head_sha`."""
    total = pending = failed = 0
    failing: list[str] = []
    for wr in repo.get_workflow_runs(head_sha=head_sha):
        total += 1
        if wr.status != "completed":
            pending += 1
        if wr.conclusion in FAIL_CONCLUSIONS:
            failed += 1
            failing.append(f"{wr.name}#{wr.id}({wr.conclusion})")
    return total, pending, failed, ", ".join(failing)


def _watch(
    logger: logging.Logger,
    repo,
    branch: str,
    head_sha: str,
    watch_timeout: int = 1200,
    poll_interval: int = 30,
) -> CiChecks:
    """The poll loop, until the runs settle or the wall-clock ceiling is reached."""
    start = time.monotonic()
    no_runs_polls = 0

    while True:
        try:
            total, pending, failed, names = _poll_runs(repo, head_sha)
        except GithubException as exc:
            settled = _auth_failure(logger, exc, branch)
            if settled is not None:
                return settled
            logger.info(
                "transient error querying Actions runs for %s (%s) — retrying", branch, exc
            )
        else:
            if total == 0:
                no_runs_polls += 1
                if no_runs_polls >= NO_RUNS_POLL_LIMIT:
                    logger.info(
                        "no Actions runs for %s@%s after %d polls — treating as no CI configured",
                        branch, head_sha, no_runs_polls,
                    )
                    return CiChecks(
                        status="unavailable", summary=f"no Actions runs for {branch}"
                    )
                logger.info(
                    "no Actions runs for %s@%s yet (poll %d) — waiting",
                    branch, head_sha, no_runs_polls,
                )
            elif pending > 0:
                logger.info(
                    "%d/%d run(s) still in progress for %s — waiting", pending, total, branch
                )
            elif failed > 0:
                names = names or f"{failed} of {total} run(s) failed"
                logger.info("CI not green for %s@%s: %s", branch, head_sha, names)
                return CiChecks(status="failed", summary=names.replace('"', "")[:300])
            else:
                logger.info(
                    "CI passed for %s@%s (%d run(s) succeeded)", branch, head_sha, total
                )
                return CiChecks(
                    status="passed", summary=f"all {total} Actions run(s) succeeded"
                )

        if time.monotonic() - start >= watch_timeout:
            logger.info(
                "CI watch timed out after %ds for %s (runs never settled)", watch_timeout, branch
            )
            return CiChecks(
                status="failed",
                summary=f"watch timed out after {watch_timeout}s (Actions runs never settled)",
            )

        time.sleep(poll_interval)


def _auth_failure(logger: logging.Logger, exc: GithubException, branch: str) -> CiChecks | None:
    """`blocked` when the token cannot read Actions, `None` when it is worth retrying."""
    err = str(getattr(exc, "data", "") or exc)
    if getattr(exc, "status", None) not in (401, 403) and not AUTH_RE.search(err):
        return None
    reason = err.replace('"', "").strip()[:200] or "GitHub auth/permission error"
    logger.warning(
        "cannot read Actions runs for %s — auth/permission error, so CI was never gated. "
        "Grant the token Actions:Read.",
        branch,
    )
    logger.warning("%s", err)
    return CiChecks(status="blocked", summary=f"CI unreadable: {reason}")


def push_epic_branch(
    logger: logging.Logger, root: Path, branch: str
) -> Literal["pushed", "unavailable", "failed"]:
    """Push `branch` from `root` over HTTPS: `pushed`, `unavailable` or `failed`."""
    if not branch:
        logger.info("no branch given — nothing to push")
        return "unavailable"
    if not branch_exists(root, branch):
        logger.info("no branch %s to push", branch)
        return "unavailable"

    token = resolve_github_token(root)
    if not token:
        logger.info(
            "no GitHub token (set workflow.githubTokenEnv in agents.yml) — leaving %s unpushed",
            branch,
        )
        return "unavailable"

    url = origin_url(root)
    if not url:
        logger.info("no 'origin' remote — leaving %s unpushed", branch)
        return "unavailable"
    if not repo_full_name_from_url(url):
        logger.info("origin '%s' is not a github.com remote — leaving %s unpushed", url, branch)
        return "unavailable"

    if not push_branch(root, token, branch):
        logger.info(
            "push failed or unverified for %s (auth/permission/network/non-fast-forward, "
            "or the remote head did not advance) — NOT silently ignored; surfacing as a failure",
            branch,
        )
        return "failed"

    logger.info("pushed %s (remote head verified)", branch)
    return "pushed"


@blueprint.node
def push_ci_fix(logger: logging.Logger, repo_dir: str, branch: str) -> PushOutcome:
    """Push the CI fix, so the next poll has a new head to judge."""
    root = Path(repo_dir) if repo_dir else find_repo_root()
    status = push_epic_branch(logger, root, branch)
    return PushOutcome(status=status, notes=f"{status} {branch} from {root}")


__all__ = [
    "branch_epic",
    "epic_branch",
    "poll_pr_checks",
    "push_ci_fix",
    "push_epic_branch",
    "select_ci_repo",
]
