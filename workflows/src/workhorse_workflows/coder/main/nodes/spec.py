"""The spec pass's hand-over: which book nodes and book paths it wrote, kept for the lanes after it."""
from __future__ import annotations

import logging

from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.docs import SpecNodes


@blueprint.node
def record_spec_nodes(
    logger: logging.Logger,
    nodes: list[str] | None = None,
    book_paths: list[str] | None = None,
) -> SpecNodes:
    """Record the markdown nodes and the executable-book paths the spec pass wrote, so dev and the build pass can read them back."""
    kept = list(dict.fromkeys(nodes or []))
    kept_paths = list(dict.fromkeys(book_paths or []))
    logger.info("the spec pass wrote %d node(s) and %d book path(s)", len(kept), len(kept_paths))
    return SpecNodes(nodes=kept, book_paths=kept_paths)


__all__ = ["record_spec_nodes"]
