"""The decision step's non-agent work: which clusters are ready, and filing one decision."""
from __future__ import annotations

import logging

from ostler import Ostler, register
from workhorse_workflows.kit import find_docs_root
from workhorse_workflows.review_debt.nodes._blueprint import blueprint
from workhorse_workflows.review_debt.schemas import Candidate, Candidates, DecisionDraft, Filed, TrendReport


def _unbound(okf: Ostler, name: str, cause: str, ids: list[str]) -> Candidate:
    """The cluster narrowed to the records on the shelf with no decision yet."""
    by_id = {r.id: r for r in okf.records().records if not r.decision}
    kept = [by_id[i] for i in ids if i in by_id]
    return Candidate(name=name, cause=cause, ids=[r.id for r in kept], lines=register.listing(kept))


@blueprint.node
def select_candidates(
    logger: logging.Logger, report: TrendReport, threshold: int, repo_dir: str = ""
) -> Candidates:
    """Find the clusters with at least *threshold* records not yet bound to a decision."""
    okf = Ostler(find_docs_root(repo_dir))
    narrowed = (_unbound(okf, c.name, c.cause, c.ids) for c in report.clusters)
    ready = [c for c in narrowed if len(c.ids) >= threshold]
    logger.info("%d of %d clusters reach the decision threshold of %d", len(ready), len(report.clusters), threshold)
    return Candidates(clusters=ready)


@blueprint.node
def narrow_candidate(logger: logging.Logger, candidate: Candidate, repo_dir: str = "") -> Candidate:
    """Drop the records of *candidate* that a decision has bound since it was selected."""
    narrowed = _unbound(Ostler(find_docs_root(repo_dir)), candidate.name, candidate.cause, candidate.ids)
    if len(narrowed.ids) < len(candidate.ids):
        logger.info("%d records of '%s' are bound already", len(candidate.ids) - len(narrowed.ids), candidate.name)
    return narrowed


@blueprint.node
def file_decision(
    logger: logging.Logger, candidate: Candidate, draft: DecisionDraft, repo_dir: str = ""
) -> Filed:
    """Propose one decision from *candidate* and bind its records; a refusal is returned, not raised."""
    result = Ostler(find_docs_root(repo_dir)).propose_decision(
        slug=draft.slug, title=draft.title, context=draft.context, decision=draft.decision,
        consequences=draft.consequences, evidence=candidate.ids,
    )
    logger.info("%s", result.message)
    return Filed(ok=result.ok, id=result.entity_id, message=result.message)
