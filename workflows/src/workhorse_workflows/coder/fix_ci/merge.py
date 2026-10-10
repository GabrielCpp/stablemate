"""The ship lane's merge: land the epic's PR, and flag it on the PR when a person must."""
from __future__ import annotations

import logging
from pathlib import Path

from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.branches import epic_branch
from workhorse_workflows.coder.shared.schemas.pr import MergeFlagged, MergeOutcome
from workhorse_workflows.kit import (
    find_open_pr,
    find_repo_root,
    origin_url,
    repo_full_name_from_url,
    resolve_github_token,
    resolve_repo,
    sync_to_origin,
)


@blueprint.node
def merge_pr(
    logger: logging.Logger, epic: str = "", base_branch: str = "main", repo_dir: str = ""
) -> MergeOutcome:
    """Merge the epic's PR into its base, then move the local checkout to the merged tip."""
    branch = epic_branch(epic)

    if not epic:
        logger.info("no epic given — nothing to merge")
        return MergeOutcome(merge_status="unavailable", base_branch=base_branch)

    root = find_repo_root(repo_dir)

    token = resolve_github_token(root)
    if not token:
        logger.info(
            "no GitHub token (set workflow.githubTokenEnv in agents.yml) — leaving %s unmerged",
            branch,
        )
        return MergeOutcome(merge_status="unavailable", base_branch=base_branch)

    url = origin_url(root)
    if not url:
        logger.info("no 'origin' remote — leaving %s unmerged", branch)
        return MergeOutcome(merge_status="unavailable", base_branch=base_branch)

    repo_path = repo_full_name_from_url(url)
    if not repo_path:
        logger.info("origin '%s' is not a github.com remote — leaving %s unmerged", url, branch)
        return MergeOutcome(merge_status="unavailable", base_branch=base_branch)

    repo, _ = resolve_repo(root, token)
    if repo is None:
        logger.info("cannot reach github.com repo %s — leaving %s unmerged", repo_path, branch)
        return MergeOutcome(merge_status="unavailable", base_branch=base_branch)

    pr = find_open_pr(repo, branch)
    if pr is None:
        if _find_merged_pr(repo, branch) is not None:
            logger.info("PR for %s already merged into %s", branch, base_branch)
            _sync_base(logger, root, base_branch, token)
            return MergeOutcome(merge_status="merged", base_branch=base_branch)
        logger.info("no open PR for %s — nothing to merge", branch)
        return MergeOutcome(merge_status="unavailable", base_branch=base_branch)

    method = _pick_merge_method(repo)
    logger.info("merging %s into %s with --%s", branch, base_branch, method)
    try:
        pr.merge(merge_method=method)
    except Exception as exc:  # noqa: BLE001 - conflict, protection or not-mergeable all read the same
        logger.info(
            "merge (--%s) failed for %s (merge conflict, branch protection, or not mergeable): "
            "%s — leaving PR open; next epic will branch from its tip",
            method, branch, exc,
        )
        return MergeOutcome(merge_status="failed", base_branch=base_branch)

    logger.info("merged %s into %s (--%s)", branch, base_branch, method)
    _sync_base(logger, root, base_branch, token)
    return MergeOutcome(merge_status="merged", base_branch=base_branch)


def _sync_base(logger: logging.Logger, root: Path, base: str, token: str) -> None:
    """Return the local checkout to `base` and pull it to the merged tip."""
    head = sync_to_origin(root, token, base)
    if head is None:
        logger.warning(
            "merged but could not sync local '%s' to the merged tip — leaving HEAD as-is; "
            "the next epic will branch from its current tip",
            base,
        )
        return
    logger.info("synced local '%s' to the merged tip (%s)", base, head)


def _pick_merge_method(repo) -> str:
    """The first merge method the repo allows, defaulting to a merge commit."""
    try:
        if repo.allow_merge_commit:
            return "merge"
        if repo.allow_squash_merge:
            return "squash"
        if repo.allow_rebase_merge:
            return "rebase"
    except Exception:  # noqa: BLE001 - an unreadable settings blob just means "assume merge"
        pass
    return "merge"


def _find_merged_pr(repo, branch: str):
    """The most recent MERGED PR for `branch` (the resume-after-merge case), else `None`."""
    owner = repo.owner.login
    for pr in repo.get_pulls(state="closed", head=f"{owner}:{branch}"):
        if pr.merged:
            return pr
    return None


@blueprint.node
def flag_merge_failure(
    logger: logging.Logger,
    epic: str = "",
    base_branch: str = "main",
    attempts: str = "?",
    repo_dir: str = "",
) -> MergeFlagged:
    """The PR could not be merged within the conflict-resolution budget."""
    branch = epic_branch(epic)
    root = find_repo_root(repo_dir)

    logger.warning(
        "%s\n"
        "⛔ MERGE FAILED — operator input required (expected, NOT a crash).\n"
        "The PR for epic '%s' (branch %s → %s) could not be merged after\n"
        "%s automated conflict-resolution attempts. The run is stopping so\n"
        "you can investigate (merge conflict, branch protection, required reviews, or\n"
        "required CI checks that have not run).\n"
        "Resolve the merge on %s, then re-run the workflow to resume.\n"
        "%s",
        "=" * 60, epic, branch, base_branch, attempts, branch, "=" * 60,
    )

    return MergeFlagged(
        merge_flagged=_comment_on_pr(
            logger,
            root,
            epic,
            branch,
            f"⛔ This PR could not be merged after {attempts} automated conflict-resolution "
            f"attempts. The coder run paused here for manual review (merge conflict, branch "
            f"behind `{base_branch}`, branch protection, or required checks that did not run).",
        )
    )


def _comment_on_pr(
    logger: logging.Logger, root: Path, epic: str, branch: str, body: str
) -> bool:
    """Post the give-up note on the epic's open PR."""
    token = resolve_github_token(root)
    if not epic or not token:
        return False
    repo, _ = resolve_repo(root, token)
    pr = find_open_pr(repo, branch) if repo is not None else None
    if pr is None:
        logger.info("PR for %s not open — nothing to comment on", branch)
        return False
    try:
        pr.create_issue_comment(body)
    except Exception as exc:  # noqa: BLE001 - a note that did not land is never worth failing on
        logger.info("could not post PR comment for %s: %s", branch, exc)
        return False
    return True


__all__ = ["flag_merge_failure", "merge_pr"]
