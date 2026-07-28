#!/usr/bin/env python3
"""Commit a completed story's changes in each affected code repo.

Commits only in repos where implementation work was done (resolved from
plan-context.json). The docs repo is never committed to by this script —
it is only committed to if it appears in the affected repos list (i.e.
if it was an implementation target, not merely the workflow host).

It is also where a story's PASSING outcome is recorded: the story's Status is
stamped ``QA passed`` (story_status.mark — frontmatter via ostler, body as the
fallback) and committed. Nothing else on the success path writes that status,
and story selection reads it, not the git log: without the stamp a story that
just passed is re-selected on the next loop iteration and its epic never reads
as complete. The give-up path stamps its own honest status in flag-qa-failure.py.

Args: <epic> <story_slug> <spec_dir> [<story_path>]
Outputs JSON: {"committed": "yes"|"no"}
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from workhorse.scriptutil import (
    commit_all,
    commit_paths,
    find_repo_root,
    fresh_import,
    get_affected_repos,
    load_json,
    resolve_workspace,
)

logger = logging.getLogger(__name__)

# Matches select.py's _DONE_TOKENS, which is what makes the story read as done to
# `ostler next-story` and to select-next-story.py's dependencies.json fallback.
DONE_STATUS = "QA passed"


def commit_in_repo(repo_path: Path, message: str) -> bool:
    """Stage all changes and commit in a repo. Returns True if a commit was made."""
    if not commit_all(repo_path, message):
        return False
    logger.info("committed in %s", repo_path.name)
    return True


def stamp_status(root: Path, epic: str, slug: str, story_path: str, message: str) -> None:
    """Record ``QA passed`` on the story and commit just that change.

    Deliberately committed SEPARATELY, scoped to the paths the stamp touched, and
    deliberately NOT folded into the caller's ``committed`` answer. That answer
    drives the zero-diff churn guard (three consecutive no-op story commits halt
    the run), and a status stamp is a change every passing story makes — counting
    it would mean every story always "committed something" and the guard could
    never trip again.

    Imported fresh so a mid-run edit to ostler is not shadowed by the copy cached
    in sys.modules from an earlier node.
    """
    story_status = fresh_import("story_status", also_purge=("ostler",))
    written = story_status.mark(
        root, slug, DONE_STATUS, epic=epic, story_path=story_path, logger=logger
    )
    if not written:
        logger.warning(
            "status '%s' NOT recorded for %s — it will be re-selected on the next loop",
            DONE_STATUS, slug,
        )
        return

    # The story doc lives in the workflow host repo (the doc graph root), which is
    # not necessarily one of the affected code repos — so it is committed here or
    # not at all. Scoped to the stamped paths so this can never sweep in unrelated
    # working-tree changes the story deliberately left alone.
    specs: list[str] = []
    for path in written:
        try:
            specs.append(str(path.resolve().relative_to(root.resolve())))
        except ValueError:
            logger.info("status file %s is outside %s — not committing it here", path, root)
    if specs and commit_paths(root, f"{message} [{DONE_STATUS}]", *specs):
        logger.info("recorded %s for %s", DONE_STATUS, slug)


def main(logger: logging.Logger) -> None:
    epic = sys.argv[1] if len(sys.argv) > 1 else ""
    slug = sys.argv[2] if len(sys.argv) > 2 else "story"
    spec_dir_rel = sys.argv[3] if len(sys.argv) > 3 else ""
    story_path_arg = sys.argv[4] if len(sys.argv) > 4 else ""

    if epic:
        message = f"{epic}: {slug}"
    else:
        message = slug

    root = find_repo_root()
    repos = resolve_workspace("CODER_WORKSPACE")

    # Resolve affected repos from plan-context.json
    spec_dir = root / spec_dir_rel if spec_dir_rel else None
    plan_ctx = load_json(spec_dir / "plan-context.json", "plan-context.json", logger) if spec_dir and spec_dir.exists() else {}
    affected_names = get_affected_repos(plan_ctx, repos)

    if not affected_names:
        # No plan-context.json or empty services — fall back to committing in the CWD repo
        # (single-repo / no-workspace-file case, and test sandboxes without a seeded plan).
        logger.info("no affected repos resolved from plan-context — falling back to CWD")
        any_committed = commit_in_repo(root, message)
    else:
        any_committed = False
        for name in affected_names:
            repo_info = repos.get(name, {})
            repo_path = Path(repo_info.get("path", ""))
            if not repo_path.is_dir():
                logger.warning("repo %s path not found: %s", name, repo_path)
                continue
            if not (repo_path / ".git").exists():
                logger.warning("repo %s is not a git repo — skipping", name)
                continue

            if commit_in_repo(repo_path, message):
                any_committed = True

    # AFTER the code commits, so the answer above measures the story's WORK and
    # nothing else (see stamp_status), and so a crash between the two leaves the
    # story un-stamped — i.e. retried — rather than marked done with no work.
    stamp_status(root, epic, slug, story_path_arg, message)

    print(json.dumps({"committed": "yes" if any_committed else "no"}))


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[commit-story] %(message)s")
    main(logging.getLogger("commit-story"))
