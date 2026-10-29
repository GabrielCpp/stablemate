"""The spec pass's hand-over: which book nodes it wrote, kept for the lanes after it."""
from __future__ import annotations

import logging

from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.docs import SpecNodes


@blueprint.node
def record_spec_nodes(logger: logging.Logger, nodes: list[str] | None = None) -> SpecNodes:
    """Record the nodes the spec pass wrote, so dev and the build pass can read them back."""
    kept = list(dict.fromkeys(nodes or []))
    logger.info("the spec pass wrote %d node(s)", len(kept))
    return SpecNodes(nodes=kept)


__all__ = ["record_spec_nodes"]
