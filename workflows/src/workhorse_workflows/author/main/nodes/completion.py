"""The completion gate's evidence: the contract the run started from, and the rows it left unfinished."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from ostler import markdown
from workhorse import gates
from workhorse.worklist import WORK_FILE, JsonBackend, WorkList
from workhorse_workflows.author.main.nodes._blueprint import blueprint
from workhorse_workflows.author.shared.paths import survey_repo_root
from workhorse_workflows.author.shared.schemas.main import Completion, ContractDigest, UnfinishedRow

ANSWER_LIMIT_CHARS = 8000


def _body_digest(root: Path, milestone_path: str) -> str:
    text = (root / milestone_path).read_text(encoding="utf-8")
    return hashlib.sha256(markdown.split(text).body.encode("utf-8")).hexdigest()


def answer_below(text: str, question: str) -> str:
    """What the operator wrote under *question* on the gate *text*, or nothing when a newer question replaced it."""
    asked = question.strip()
    latest = gates.latest_question(text, limit=len(asked) + ANSWER_LIMIT_CHARS)
    if not asked or not latest.startswith(asked):
        return ""
    return latest[len(asked):].removesuffix(gates.TRUNCATION_NOTE).strip()


@blueprint.node
def contract_digest(
    logger: logging.Logger,
    milestone_path: str,
    repo_dir: str = "",
) -> ContractDigest:
    """The sha256 of the milestone body, which the run never writes, so a change is an operator's edit."""
    digest = _body_digest(survey_repo_root(repo_dir), milestone_path)
    logger.info("milestone contract digest %s", digest[:12])
    return ContractDigest(digest=digest)


@blueprint.node
def check_completion(
    logger: logging.Logger,
    milestone_path: str,
    baseline: str,
    run_dir: str,
    repo_dir: str = "",
) -> Completion:
    """Whether the milestone body still matches *baseline*, and every work-list row not yet done."""
    digest = _body_digest(survey_repo_root(repo_dir), milestone_path)
    work = WorkList(JsonBackend(Path(run_dir) / WORK_FILE))
    unfinished = [
        UnfinishedRow(kind=item.kind, id=item.id, status=item.status or "pending", laps=item.laps)
        for item in work.items()
        if item.status != "done"
    ]
    logger.info("%d work rows unfinished", len(unfinished))
    return Completion(matches=digest == baseline, digest=digest, unfinished=unfinished)


__all__ = ["answer_below", "check_completion", "contract_digest"]
