"""Persist semantic story-graph approval after the coverage reviewer passes it."""
from __future__ import annotations

import json
import logging

from ostler import Ostler
from ostler.select import epic_by_name
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.author.shared.paths import survey_repo_root
from workhorse_workflows.author.shared.story_split_receipt import (
    story_split_digest,
    story_split_receipt_path,
)
from workhorse_workflows.author.story_split.nodes._blueprint import blueprint
from workhorse_workflows.author.story_split.schemas import StorySplitReceipt


@blueprint.node
def record_story_split_review(
    logger: logging.Logger,
    epic: str,
    repo_dir: str = "",
) -> StorySplitReceipt:
    """Bind a passing semantic review to the current seeds and story topology."""
    root = survey_repo_root(repo_dir)
    found = epic_by_name(Ostler(root).graph, epic)
    if found is None:
        raise WorkflowFailed(f"cannot record story-split review: no epic named '{epic}'")
    receipt = story_split_receipt_path(found)
    if receipt is None:
        raise WorkflowFailed(f"cannot record story-split review: epic '{epic}' has no epic.md")
    digest = story_split_digest(found)
    receipt.write_text(
        json.dumps({"status": "passed", "graphDigest": digest}, indent=2) + "\n",
        encoding="utf-8",
    )
    relative = receipt.relative_to(root).as_posix()
    logger.info("recorded passing story-split review at %s", relative)
    return StorySplitReceipt(graph_digest=digest, path=relative)


__all__ = ["record_story_split_review"]
