"""Write the PM's pass beside the output it judged."""
from __future__ import annotations

import logging

from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.author.pm.nodes._blueprint import blueprint
from workhorse_workflows.author.pm.receipt import receipt_target, write_pm_receipt
from workhorse_workflows.author.pm.schemas import PMReceipt
from workhorse_workflows.author.shared.paths import survey_repo_root


@blueprint.node
def record_pm_receipt(
    logger: logging.Logger,
    stage: str,
    subject: str,
    repo_dir: str = "",
) -> PMReceipt:
    """Bind a passing review to the exact bytes it judged, for the stages whose output is a durable file."""
    root = survey_repo_root(repo_dir)
    try:
        target = receipt_target(root, stage, subject)
    except OSError as exc:
        raise WorkflowFailed(f"cannot record the {stage} receipt for '{subject}': {exc}") from exc
    if target is None:
        logger.info("the %s stage keeps no receipt", stage)
        return PMReceipt()
    directory, digest = target
    path = write_pm_receipt(directory, stage, digest)
    relative = path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix()
    logger.info("recorded the passing %s review at %s", stage, relative)
    return PMReceipt(path=relative, digest=digest)


__all__ = ["record_pm_receipt"]
