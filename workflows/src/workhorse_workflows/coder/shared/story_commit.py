"""The clean-tree check, the commit that records a passed story, and its stamp."""
from __future__ import annotations

import logging
from pathlib import Path

from ostler import registry
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.coder.shared import commits, paths, story_status
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.plan import get_affected_repos, load_plan_context
from workhorse_workflows.coder.shared.schemas.queue import (
    StoryCommitted,
    StoryStamped,
    WorktreeCleanliness,
)
from workhorse_workflows.coder.shared.worktree import untouched_since
from workhorse_workflows.kit import (
    GitError,
    commit_all,
    commit_paths,
    find_repo_root,
    open_repo,
    resolve_workspace,
)

DONE_STATUS = "QA passed"


def _stamp_status(
    logger: logging.Logger, root: Path, epic: str, slug: str, story_path: str
) -> tuple[bool, bool]:
    """Record `QA passed` on the story and commit just that change."""
    before = story_status.current(root, slug, epic=epic, story_path=story_path)
    written = story_status.mark(root, slug, DONE_STATUS, epic=epic, story_path=story_path, logger=logger)
    if not written:
        logger.warning(
            "status '%s' NOT recorded for %s — it will be re-selected on the next loop",
            DONE_STATUS,
            slug,
        )
        return False, False
    prior = before.strip()
    superseded = bool(prior) and prior not in (registry.DEFAULT_STORY_STATUS, DONE_STATUS)

    specs: list[str] = []
    for path in written:
        try:
            specs.append(str(path.resolve().relative_to(root.resolve())))
        except ValueError:
            logger.info("status file %s is outside %s — not committing it here", path, root)
    stamp = commits.message(
        "docs",
        commits.scope(root.name),
        f"mark {slug} {DONE_STATUS}",
        epic=epic,
        story=slug,
    )
    if specs and commit_paths(root, stamp, *specs):
        logger.info("recorded %s for %s", DONE_STATUS, slug)
    return True, superseded


def _commit_roots(
    logger: logging.Logger,
    root: Path,
    spec_dir: str,
    workspace_file: str,
    repo_dir: str,
    roots: list[str] | None,
) -> list[tuple[str, Path]]:
    """Which checkouts this story's commit covers — the caller's list, or the plan's."""
    if roots:
        return [(Path(p).name, Path(p)) for p in roots]
    return _affected_roots(logger, root, spec_dir, workspace_file, repo_dir)


def _affected_roots(
    logger: logging.Logger, root: Path, spec_dir: str, workspace_file: str, repo_dir: str
) -> list[tuple[str, Path]]:
    """The repos this story's plan says it touched, as `(package name, checkout)` pairs."""
    repos = resolve_workspace(workspace_file, repo_dir)
    plan_ctx = load_plan_context(root, spec_dir, logger)
    affected = get_affected_repos(plan_ctx, repos)
    if not affected:
        logger.info("no affected repos resolved from plan-context — falling back to the repo root")
        return [(root.name, root)]

    found: list[tuple[str, Path]] = []
    for name in affected:
        repo_path = Path(repos.get(name, {}).get("path", ""))
        if not repo_path.is_dir():
            logger.warning("repo %s path not found: %s", name, repo_path)
            continue
        if not (repo_path / ".git").exists():
            logger.warning("repo %s is not a git repo — skipping", name)
            continue
        found.append((name, repo_path))
    return found


def _uncommitted(root: Path) -> list[str]:
    """Every path in *root* holding work that is not in a commit yet."""
    try:
        repo = open_repo(root)
        dirty = {item.a_path for item in repo.index.diff(None) if item.a_path}
        dirty |= set(repo.untracked_files)
        try:
            dirty |= {item.a_path for item in repo.index.diff("HEAD") if item.a_path}
        except (GitError, OSError, TypeError, ValueError, KeyError):
            pass
    except (GitError, OSError, TypeError, ValueError, RuntimeError):
        return []
    return sorted(dirty)


@blueprint.node
def check_repos_clean(
    logger: logging.Logger,
    story_slug: str = "",
    spec_dir: str = "",
    preexisting: list[str] | None = None,
    repo_dir: str = "",
    workspace_file: str = "",
) -> WorktreeCleanliness:
    """Did the agent commit its own work in every repo the story touched?"""
    root = find_repo_root(repo_dir)
    snapshot = tuple(preexisting or ())
    dirty: list[str] = []
    names: list[str] = []
    for name, repo_path in _affected_roots(logger, root, spec_dir, workspace_file, repo_dir):
        names.append(name)
        excused = untouched_since(repo_path, snapshot)
        dirty.extend(
            f"{name}:{rel}"
            for rel in _uncommitted(repo_path)
            if rel not in excused and not paths.is_gate_context(rel)
        )

    slug = story_slug or "story"
    if dirty:
        logger.info(
            "%s left %d uncommitted path(s) behind: %s",
            slug, len(dirty), ", ".join(dirty[:10]) + (" …" if len(dirty) > 10 else ""),
        )
    else:
        logger.info("%s left nothing uncommitted in %s", slug, ", ".join(names) or "the repo root")
    return WorktreeCleanliness(clean=not dirty, dirty=dirty, repos=names)


@blueprint.node
def stamp_story_passed(
    logger: logging.Logger,
    epic: str = "",
    story_slug: str = "",
    story_path: str = "",
    repo_dir: str = "",
) -> StoryStamped:
    """Record the story's passing outcome, and commit that one line."""
    slug = story_slug or "story"
    root = find_repo_root(repo_dir)
    stamped, superseded = _stamp_status(logger, root, epic, slug, story_path)
    return StoryStamped(stamped=stamped, superseded_outcome=superseded)


@blueprint.node
def commit_story(
    logger: logging.Logger,
    epic: str = "",
    story_slug: str = "",
    spec_dir: str = "",
    story_path: str = "",
    repo_dir: str = "",
    workspace_file: str = "",
    kind: str = "feat",
    roots: list[str] | None = None,
    story_id: str = "",
) -> StoryCommitted:
    """Commit a completed story's changes in each affected code repo, then stamp it passed."""
    slug = story_slug or "story"
    root = find_repo_root(repo_dir)

    epic_name = registry.epic_slug(epic) or epic
    description = commits.story_description(root, story_path, slug)

    def _story_message(package: str) -> str:
        return commits.message(
            kind, commits.scope(package), description, epic=epic_name, story=story_id or slug
        )

    def _commit_in(repo_path: Path, package: str) -> bool:
        """``commit_all``, with a git refusal turned into a halt rather than a False."""
        try:
            return bool(commit_all(repo_path, _story_message(package)))
        except GitError as exc:
            raise WorkflowFailed(
                f"git refused the commit for {slug} in {repo_path}: {exc}"
            ) from exc

    any_committed = False
    for name, repo_path in _commit_roots(logger, root, spec_dir, workspace_file, repo_dir, roots):
        if _commit_in(repo_path, name):
            logger.info("committed in %s", repo_path.name)
            any_committed = True

    _, superseded = _stamp_status(logger, root, epic, slug, story_path)
    return StoryCommitted(committed=any_committed, superseded_outcome=superseded)


__all__ = [
    "check_repos_clean",
    "commit_story",
    "stamp_story_passed",
]
