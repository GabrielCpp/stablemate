"""Normalize backlog identity before an agent reads the worklist."""
from __future__ import annotations

import logging

from ostler import Ostler
from ostler.result import Result
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.author.main.nodes._blueprint import blueprint
from workhorse_workflows.author.shared.paths import survey_repo_root


@blueprint.node
def adopt_backlog(
    logger: logging.Logger,
    backlog: str = "",
    repo_dir: str = "",
) -> Result:
    """Mint ids for every unnamed backlog bullet before decomposition or story lookup."""
    result = Ostler(survey_repo_root(repo_dir)).backlog_adopt(backlog)
    if not result.ok:
        raise WorkflowFailed(result.message)
    logger.info(result.message)
    return result


__all__ = ["adopt_backlog"]
