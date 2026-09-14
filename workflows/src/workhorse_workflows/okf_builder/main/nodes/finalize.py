"""The scoped git commits that record the OKF book: one per turn, and the completed book.

**Every commit here skips the target repo's hooks.** A repo's `pre-commit` and
`commit-msg` hooks are written for whoever changes its code. This workflow commits only
the book it alone writes, and has gated that book with its own doctor. The hook that
blocked it was a generated-file drift check over the whole working tree, so an unrelated
hand edit anywhere in the checkout stopped every book commit (`kit.git.commit_paths`).

**Why a commit per turn.** A run used to leave the book uncommitted until it was clean,
often for days. `HEAD` then predated every edit the run had made, and a repair turn that
restored a file from `HEAD` to undo its own change erased the run's earlier repairs with
it. `commit_turn` runs before and after every turn, so `HEAD` is where the turn started
and `git diff -- <book>` is exactly what the turn wrote. The pre-turn call records
whatever deterministic nodes wrote to the book since the last turn. The post-turn call
records the turn under the subject the turn wrote, because the turn is the only
participant that knows what it changed.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from git.exc import GitError

from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.kit import commit_paths
from workhorse_workflows.okf_builder.shared.blueprint import blueprint
from workhorse_workflows.okf_builder.shared.schemas import Committed

_SUBJECT = "docs: update the OKF book"
_SUBJECT_MAX = 72

#: Seconds between attempts when another process holds the index lock.
_LOCK_BACKOFF_S = (1.0, 2.0, 4.0, 8.0)


def _message(story: str, subject: str = _SUBJECT) -> str:
    lines = subject.strip().splitlines()
    head = (lines[0].strip() if lines else "") or _SUBJECT
    if len(head) > _SUBJECT_MAX:
        head = head[: _SUBJECT_MAX - 1].rstrip() + "…"
    story = story.strip()
    return f"{head}\n\nStory: {story}" if story else head


def _book_pathspec(root: Path, features_root: str) -> str:
    book = Path(features_root).resolve()
    try:
        return str(book.relative_to(root))
    except ValueError as exc:
        raise WorkflowFailed(
            f"refusing to commit OKF book outside its repository: {book} is not under {root}",
            failure_class="okf-builder-book-outside-repo",
        ) from exc


@blueprint.node
def commit_turn(
    logger: logging.Logger,
    repo_root: str,
    features_root: str,
    subject: str,
    story: str = "",
    lock_retries: int = len(_LOCK_BACKOFF_S),
) -> Committed:
    """Commit whatever changed in the book, under `subject`; never fail the run.

    A refused commit leaves the edits in the tree, and the next call's scope is the same
    book, so they land with the next commit. The hard stop belongs to `commit_book`, the
    commit that must land. Several runs in one checkout share one index, so a held
    `index.lock` is expected and waited out. That shared index is the property this retry
    handles rather than removes: a run dispatched with `--worktree` has its own index and
    never waits here.
    """
    root = Path(repo_root).resolve()
    pathspec = _book_pathspec(root, features_root)
    message = _message(story, subject)
    for attempt in range(lock_retries + 1):
        try:
            committed = commit_paths(root, message, pathspec, verify=False)
        except GitError as exc:
            locked = "index.lock" in str(exc)
            if locked and attempt < lock_retries:
                time.sleep(_LOCK_BACKOFF_S[min(attempt, len(_LOCK_BACKOFF_S) - 1)])
                continue
            logger.warning(
                "could not commit %s (%s); its edits stay in the tree for the next commit: %s",
                pathspec, "index locked" if locked else "git refused", exc,
            )
            return Committed(committed=False)
        if committed:
            logger.info("committed %s: %s", pathspec, message.splitlines()[0])
        return Committed(committed=committed)
    return Committed(committed=False)


@blueprint.node
def commit_book(
    logger: logging.Logger,
    repo_root: str,
    features_root: str,
    story: str = "",
) -> Committed:
    """Commit only the completed service book, with optional story provenance."""
    root = Path(repo_root).resolve()
    book_pathspec = _book_pathspec(root, features_root)
    committed = commit_paths(root, _message(story), book_pathspec, verify=False)
    logger.info(
        "%s completed OKF book at %s",
        "committed" if committed else "no changes in",
        book_pathspec,
    )
    return Committed(committed=committed)


__all__ = ["commit_book", "commit_turn"]
