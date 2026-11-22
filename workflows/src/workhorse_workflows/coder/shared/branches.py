"""The run branch and the code repos put on it: its name, its base, and cutting it."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from workhorse._vendor.stablemate_core import book_branch, config as core_config
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.plan import get_affected_repos, plan_context
from workhorse_workflows.coder.shared.schemas.dev import BranchOutcome
from workhorse_workflows.coder.shared.schemas.queue import RunBranch
from workhorse_workflows.kit import (
    active_branch,
    branch_exists,
    checkout,
    current_branch,
    default_branch,
    find_docs_root,
    find_repo_root,
    local_branch_exists,
    resolve_workspace,
)

EPIC_PREFIX = "feat/"


def epic_branch(epic: str) -> str:
    """The `feat/<name>` branch a run's work lives on, and the one its PR is opened from."""
    return f"{EPIC_PREFIX}{epic}" if epic else ""


def epic_of_branch(branch: str) -> str:
    """The epic an epic branch belongs to — `epic_branch` read the other way."""
    return branch.removeprefix(EPIC_PREFIX)


def _resolve_trunk(root: Path) -> str:
    """The repo's trunk: `origin/HEAD`, else local `main`, else local `master`, else `main`."""
    trunk = default_branch(root)
    if trunk:
        return trunk
    if branch_exists(root, "main"):
        return "main"
    if branch_exists(root, "master"):
        return "master"
    return "main"


def _resolve_base(logger: logging.Logger, root: Path) -> str:
    """The branch the run's PR targets: the active branch, or trunk when that is a feature branch."""
    base = active_branch(root)
    if not base or base.startswith((EPIC_PREFIX, "rewrite/")):
        base = _resolve_trunk(root)
    logger.info("base branch is '%s'", base)
    return base


def _branch_repo(repo_path: Path, repo_name: str, branch: str, logger: logging.Logger) -> str:
    """Put one repo on `branch`: `branched`, `already_on_branch` or `skipped`."""
    if not (repo_path / ".git").exists():
        logger.warning("%s: not a git repo, skipping", repo_name)
        return "skipped"
    if current_branch(repo_path) == branch:
        logger.info("%s: already on %s", repo_name, branch)
        return "already_on_branch"
    if local_branch_exists(repo_path, branch):
        checkout(repo_path, branch)
        logger.info("%s: checked out existing %s", repo_name, branch)
    else:
        checkout(repo_path, branch, create=True)
        logger.info("%s: created %s", repo_name, branch)
    return "branched"


def is_artifacts_repo(folder: Path) -> bool:
    """Whether *folder* is a checkout of the repository that tracks the artifacts folder."""
    top = core_config.artifacts_toplevel()
    return top is not None and core_config.repository_identity(folder).main_folder == top


def book_worktree(branch: str) -> Path | None:
    """The worktree of the artifacts repository checked out on *branch*, or None when there is none."""
    top = core_config.artifacts_toplevel()
    if top is None:
        return None
    found = core_config.checkout_on(top, branch)
    return found if found != top else None


def land_book(logger: logging.Logger, branch: str) -> None:
    """Land the book branch on the artifacts base and log what happened; a refusal is only logged."""
    try:
        landing, _ = book_branch.close_book_branch(branch)
    except core_config.ConfigError as exc:
        logger.warning("the book branch %s did not land: %s", branch, exc)
        return
    files = f" ({', '.join(landing.files)})" if landing.files else ""
    logger.info("book %s %s: %s%s", landing.action, branch, landing.reason, files)


@blueprint.node
def cut_run_branch(
    logger: logging.Logger,
    name: str = "",
    repo_dir: str = "",
) -> RunBranch:
    """Put the docs repo on `feat/<name>`, the one branch every item of the run lands on, and open the book branch beside it."""
    docs_root = find_docs_root(repo_dir)
    repo = find_repo_root(repo_dir)
    identity = core_config.repository_identity(repo)
    if identity.folder != identity.main_folder:
        branch = current_branch(repo)
        logger.info("a worktree run keeps its branch %s; nothing is cut", branch)
        book_branch.open_book_branch(repo, branch)
        return RunBranch(base_branch=_resolve_base(logger, docs_root), branch=branch)
    base = _resolve_base(logger, docs_root)
    branch = epic_branch(name)
    if not is_artifacts_repo(docs_root):
        if _branch_repo(docs_root, docs_root.name, branch, logger) == "skipped":
            raise WorkflowFailed(f"cannot cut {branch}: {docs_root} is not a git repo")
    book_branch.open_book_branch(repo, branch)
    return RunBranch(base_branch=base, branch=branch)


@blueprint.node
def branch_code_repos(
    logger: logging.Logger,
    spec_dir: str = "",
    branch: str = "",
    repo_dir: str = "",
    workspace: str = "",
    plan: dict[str, Any] | None = None,
) -> BranchOutcome:
    """Put every code repo the plan names onto the run branch."""
    docs_root = find_docs_root(repo_dir)
    repos = resolve_workspace(workspace, repo_dir)
    plan_ctx, _ = plan_context(plan, spec_dir, docs_root, repos, logger)

    if not branch:
        if (docs_root / ".git").exists():
            branch = current_branch(docs_root)
        else:
            branch = "main"
            logger.warning(
                "docs root %s is not a git repo and no branch given — defaulting to 'main'",
                docs_root,
            )

    branched: list[str] = []
    already: list[str] = []
    for repo_name in get_affected_repos(plan_ctx, repos):
        repo_path = Path(repos[repo_name]["path"])
        if repo_path == docs_root:
            continue
        result = _branch_repo(repo_path, repo_name, branch, logger)
        if result == "branched":
            branched.append(repo_name)
        elif result == "already_on_branch":
            already.append(repo_name)

    return BranchOutcome(branched=branched, already_on_branch=already)


__all__ = [
    "book_worktree",
    "branch_code_repos",
    "cut_run_branch",
    "epic_branch",
    "epic_of_branch",
    "is_artifacts_repo",
    "land_book",
]
