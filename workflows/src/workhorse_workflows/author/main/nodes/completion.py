"""The completion gate's evidence: the contract and the epics the run started from, and the rows it left unfinished."""
from __future__ import annotations

import logging
from pathlib import Path

from workhorse.worklist import WORK_FILE, JsonBackend, WorkList
from workhorse_workflows.author.main.nodes._blueprint import blueprint
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.baseline import epic_scopes
from workhorse_workflows.author.shared.digests import milestone_body_digest
from workhorse_workflows.author.shared.paths import launch_repo_root, survey_repo_root
from workhorse_workflows.author.shared.schemas.main import (
    Completion,
    ContractDigest,
    EpicBaseline,
    EpicScope,
    UnfinishedRow,
)


@blueprint.node
def contract_digest(
    logger: logging.Logger,
    milestone_path: str,
    repo_dir: str = "",
) -> ContractDigest:
    """The sha256 of the milestone body, which the run never writes, so a change is an operator's edit."""
    digest = milestone_body_digest(survey_repo_root(repo_dir), milestone_path)
    logger.info("milestone contract digest %s", digest[:12])
    return ContractDigest(digest=digest)


@blueprint.node
def snapshot_epics(logger: logging.Logger, repo_dir: str = "") -> EpicBaseline:
    """Each epic's seed ids and story slugs as the run found them, for the reconcile gate to measure drops against."""
    root = launch_repo_root(repo_dir)
    epics_path = root / paths.epics_dir(root)
    scopes = epic_scopes(epics_path) if epics_path.is_dir() else {}
    logger.info("%d epic(s) at run start", len(scopes))
    return EpicBaseline(
        epics={
            epic: EpicScope(seeds=sorted(seeds), stories=sorted(stories))
            for epic, (seeds, stories) in scopes.items()
        }
    )


@blueprint.node
def check_completion(
    logger: logging.Logger,
    milestone_path: str,
    baseline: str,
    run_dir: str,
    repo_dir: str = "",
) -> Completion:
    """Whether the milestone body still matches *baseline*, and every work-list row not yet done."""
    digest = milestone_body_digest(survey_repo_root(repo_dir), milestone_path)
    work = WorkList(JsonBackend(Path(run_dir) / WORK_FILE))
    unfinished = [
        UnfinishedRow(
            kind=item.kind,
            id=item.id,
            status=item.status or "pending",
            laps=item.laps,
            note=item.note,
        )
        for item in work.items()
        if item.status != "done"
    ]
    logger.info("%d work rows unfinished", len(unfinished))
    return Completion(matches=digest == baseline, digest=digest, unfinished=unfinished)


__all__ = ["check_completion", "contract_digest", "snapshot_epics"]
