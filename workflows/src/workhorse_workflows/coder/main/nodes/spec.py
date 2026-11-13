"""The spec pass's hand-over: which book paths it wrote, kept for the lanes after it."""
from __future__ import annotations

import logging

from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.docs import SpecBookPaths


@blueprint.node
def record_spec_book_paths(
    logger: logging.Logger,
    book_paths: list[str] | None = None,
) -> SpecBookPaths:
    """Record the executable-book paths the spec pass wrote, so dev can read them back."""
    kept = list(dict.fromkeys(book_paths or []))
    logger.info("the spec pass wrote %d book path(s)", len(kept))
    return SpecBookPaths(book_paths=kept)


__all__ = ["record_spec_book_paths"]
