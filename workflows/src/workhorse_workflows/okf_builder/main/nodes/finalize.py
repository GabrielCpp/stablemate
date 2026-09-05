"""The scoped git tail that records a completed OKF book."""
from __future__ import annotations

import logging
from pathlib import Path

from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.kit import commit_paths
from workhorse_workflows.okf_builder.shared.blueprint import blueprint
from workhorse_workflows.okf_builder.shared.schemas import Committed

_SUBJECT = "docs: update the OKF book"


def _message(story: str) -> str:
    story = story.strip()
    return f"{_SUBJECT}\n\nStory: {story}" if story else _SUBJECT


@blueprint.node
def commit_book(
    logger: logging.Logger,
    repo_root: str,
    features_root: str,
    story: str = "",
) -> Committed:
    """Commit only the completed service book, with optional story provenance."""
    root = Path(repo_root).resolve()
    book = Path(features_root).resolve()
    try:
        book_pathspec = str(book.relative_to(root))
    except ValueError as exc:
        raise WorkflowFailed(
            f"refusing to commit OKF book outside its repository: {book} is not under {root}",
            failure_class="okf-builder-book-outside-repo",
        ) from exc

    committed = commit_paths(root, _message(story), book_pathspec)
    logger.info(
        "%s completed OKF book at %s",
        "committed" if committed else "no changes in",
        book_pathspec,
    )
    return Committed(committed=committed)


__all__ = ["commit_book"]
