"""The epic and story branches: their names, cutting them, the claim ledger, catching up with base."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ostler import markdown
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.coder.shared import commits, paths
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.plan import get_affected_repos, load_plan_context, plan_context
from workhorse_workflows.coder.shared.schemas.dev import BranchOutcome
from workhorse_workflows.coder.shared.schemas.queue import BaseBranch, EpicBranch, StoryBranch
from workhorse_workflows.kit import (
    active_branch,
    branch_exists,
    branch_merged,
    branch_owner,
    checkout,
    commit_paths,
    current_branch,
    default_branch,
    find_docs_root,
    find_repo_root,
    is_ancestor,
    local_branch_exists,
    merge_ref,
    resolve_workspace,
    restore_paths,
    show_file,
)

EPIC_PREFIX = "feat/"

CLAIMED_FILE = "epic-branches.txt"


def epic_branch(epic: str) -> str:
    """The branch an epic's work lives on — the one its PR is opened from."""
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


@blueprint.node
def init_base(logger: logging.Logger, repo_dir: str = "") -> BaseBranch:
    """Resolve the branch an epic's PR will be opened against, before anything is cut."""
    root = find_repo_root(repo_dir)
    base = active_branch(root)
    if not base or base.startswith((EPIC_PREFIX, "rewrite/")):
        base = _resolve_trunk(root)
    logger.info("base branch is '%s'", base)
    return BaseBranch(base_branch=base)


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


@blueprint.node
def branch_story(
    logger: logging.Logger,
    story: str = "",
    docs_path: str = "",
    spec_dir: str = "",
    repo_dir: str = "",
    workspace_file: str = "",
) -> StoryBranch:
    """Cut the working branch for a single story, in the docs repo and every affected repo."""
    slug = story or "story"
    branch = slug
    docs_root = find_docs_root(docs_path, repo_dir)

    base_branch = "main"
    if (docs_root / ".git").exists():
        base_branch = current_branch(docs_root)
        if not base_branch or base_branch == branch:
            base_branch = "main"

    branched: list[str] = []
    if _branch_repo(docs_root, docs_root.name, branch, logger) != "skipped":
        branched.append(docs_root.name)

    plan_ctx = load_plan_context(docs_root, spec_dir or f"docs/specs/{slug}", logger)
    repos = resolve_workspace(workspace_file, repo_dir)
    for repo_name in get_affected_repos(plan_ctx, repos):
        repo_path = Path(repos[repo_name]["path"])
        if repo_path == docs_root:
            continue
        if _branch_repo(repo_path, repo_name, branch, logger) != "skipped":
            branched.append(repo_name)

    return StoryBranch(base_branch=base_branch, story_branch=branch, repos=branched)


@blueprint.node
def branch_code_repos(
    logger: logging.Logger,
    spec_dir: str = "",
    branch: str = "",
    docs_path: str = "",
    repo_dir: str = "",
    workspace_file: str = "",
    plan: dict[str, Any] | None = None,
) -> BranchOutcome:
    """Put every code repo the plan names onto the story branch."""
    docs_root = find_docs_root(docs_path, repo_dir)
    repos = resolve_workspace(workspace_file, repo_dir)
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


def _claimed_branches(run_dir: str) -> set[str]:
    """The epic branches this run has already put itself on."""
    if not run_dir:
        return set()
    try:
        text = (Path(run_dir) / CLAIMED_FILE).read_text(encoding="utf-8")
    except OSError:
        return set()
    return {line.strip() for line in text.splitlines() if line.strip()}


def _record_claim(run_dir: str, branch: str) -> None:
    """Remember that this run owns `branch`, so a later visit recognises it."""
    if not run_dir or not branch:
        return
    path = Path(run_dir)
    if not path.is_dir():
        return
    claimed = _claimed_branches(run_dir)
    if branch in claimed:
        return
    (path / CLAIMED_FILE).write_text(
        "\n".join(sorted(claimed | {branch})) + "\n", encoding="utf-8"
    )


def _claim_epic_branch(
    logger: logging.Logger, root: Path, branch: str, base: str, run_dir: str = ""
) -> None:
    """Put this run on `feat/<epic>`, or refuse and say why."""
    if not branch_exists(root, branch):
        if not checkout(root, branch, create=True):
            raise WorkflowFailed(f"failed to create epic branch {branch}")
        _record_claim(run_dir, branch)
        return

    owner = branch_owner(root, branch)
    if owner is not None:
        if Path(owner).resolve() != Path(root).resolve():
            raise WorkflowFailed(
                f"{branch} is checked out in another working tree ({owner}) — another "
                f"run is working this epic. Wait for it, or run a different epic."
            )
        logger.info("resuming %s, already checked out here", branch)
        _record_claim(run_dir, branch)
        return

    if branch in _claimed_branches(run_dir):
        logger.info("returning to %s, which this run cut earlier", branch)
        if not checkout(root, branch):
            raise WorkflowFailed(f"failed to return to epic branch {branch}")
        _catch_up_with_base(logger, root, branch, base)
        return

    if branch_merged(root, branch, base):
        logger.info("%s is already merged into %s — reusing the name from HEAD", branch, base)
        if not checkout(root, branch, reset=True):
            raise WorkflowFailed(f"failed to reset merged epic branch {branch}")
        return

    raise WorkflowFailed(
        f"{branch} already exists with commits that are not in {base or 'the base branch'}. "
        f"That is unmerged work this run did not create — merge it, or delete the branch, "
        f"then start the epic again."
    )


def _base_ref(root: Path, base: str) -> str:
    """`base` as it resolves in this repo — the local branch, else `origin/<base>`, else ""."""
    if not base:
        return ""
    for ref in (base, f"origin/{base}") if "/" not in base else (base,):
        if branch_exists(root, ref):
            return ref
    return ""


def _catch_up_with_base(logger: logging.Logger, root: Path, branch: str, base: str) -> None:
    """Bring `base` into an epic branch this run cut before `base` moved on without it."""
    ref = _base_ref(root, base)
    if not ref or is_ancestor(root, ref, branch):
        return
    if not merge_ref(root, ref):
        raise WorkflowFailed(
            f"{ref} does not merge cleanly into {branch}, which this run cut before {ref} "
            f"moved. Two epics edited the same lines — resolve it by hand, then start the "
            f"epic again."
        )
    logger.info("merged %s into %s, which had been set aside while %s moved", ref, branch, ref)


def _has_queue_bullet(content: str) -> bool:
    """Whether *content* holds at least one `- [epic](…)` queue entry."""
    return any(b.bracketed[0] for b in markdown.split(content).walk_bullets())


def _reconcile_queue(logger: logging.Logger, root: Path, base: str) -> None:
    """Restore the epic queue from `base`, when `base` has an authoritative copy of it."""
    if not base or not branch_exists(root, base):
        return
    queue_rel = paths.epics_index(root)
    content = show_file(root, base, queue_rel)
    if content is None or not content.strip() or not _has_queue_bullet(content):
        return
    if not content.endswith("\n"):
        content += "\n"
    (root / queue_rel).write_text(content, encoding="utf-8")
    reconcile = commits.message(
        "chore", commits.scope(root.name), f"reconcile the epic queue to {base}"
    )
    if commit_paths(root, reconcile, queue_rel):
        logger.info("reconciled index.md to %s", base)


@blueprint.node
def branch_epic(
    logger: logging.Logger,
    epic: str = "",
    base_branch: str = "",
    run_dir: str = "",
    repo_dir: str = "",
) -> EpicBranch:
    """Put this run on `feat/<epic>`, cutting it from HEAD when it does not exist yet."""
    root = find_repo_root(repo_dir)
    restore_paths(root, paths.epics_index(root))

    branch = epic_branch(epic)
    if epic:
        _claim_epic_branch(logger, root, branch, base_branch, run_dir.strip())

    _reconcile_queue(logger, root, base_branch)
    return EpicBranch(working_epic=epic, epic_branch=branch)


__all__ = [
    "branch_code_repos",
    "branch_epic",
    "branch_story",
    "epic_branch",
    "epic_of_branch",
    "init_base",
]
