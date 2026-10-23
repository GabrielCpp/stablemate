"""Accounting: the report covers the read, each id once."""
from __future__ import annotations

import logging
from collections import Counter

from workhorse_workflows.review_debt.nodes._blueprint import blueprint
from workhorse_workflows.review_debt.schemas import Accounting, TrendReport


@blueprint.node
def account(logger: logging.Logger, read_ids: list[str], report: TrendReport) -> Accounting:
    """Find the read ids a report leaves out, repeats, or invents."""
    reported = Counter(i for cluster in report.clusters for i in cluster.ids)
    reported.update(s.id for s in report.singletons)
    wanted = set(read_ids)
    accounting = Accounting(
        missing=[i for i in read_ids if i not in reported],
        duplicated=sorted(i for i, n in reported.items() if n > 1 and i in wanted),
        unknown=sorted(i for i in reported if i not in wanted),
    )
    if not accounting.ok:
        logger.info(
            "report off by missing=%s duplicated=%s unknown=%s",
            accounting.missing, accounting.duplicated, accounting.unknown,
        )
    return accounting
