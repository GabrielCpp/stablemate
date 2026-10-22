"""Append an answer to the milestone's PM ledger."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.author.pm.ledger import append_entry
from workhorse_workflows.author.pm.nodes._blueprint import blueprint
from workhorse_workflows.author.pm.schemas import LedgerEntry


@blueprint.node
def append_ledger(
    logger: logging.Logger,
    ledger: str,
    asker: str,
    question: str,
    answer: str,
    by: Literal["pm", "human"] = "pm",
) -> LedgerEntry:
    """Record one answered question in `grills/pm.md`, which only ever grows."""
    if not ledger.strip():
        raise WorkflowFailed("the run has no approved milestone to keep an answer for")
    append_entry(Path(ledger), asker, question, answer, by)
    logger.info("recorded the answer of the %s to %s in %s", by, asker, ledger)
    return LedgerEntry(path=ledger)


__all__ = ["append_ledger"]
