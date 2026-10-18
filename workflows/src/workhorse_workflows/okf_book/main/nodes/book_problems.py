"""The page check as the node the main flow calls, so a dry run can stand in for it."""
from __future__ import annotations

import logging
from pathlib import Path

from workhorse_workflows.okf_book.shared.blueprint import blueprint
from workhorse_workflows.okf_book.shared.page_check import PageProblem, page_problems


def _clean_in_dry_run(_logger: logging.Logger, *_args: object) -> tuple[PageProblem, ...]:
    return ()


@blueprint.node(stub=_clean_in_dry_run)
def book_problems(logger: logging.Logger, root: Path, service: str, source_folder: str) -> tuple[PageProblem, ...]:
    """Every problem on the service's book. A dry run reads no page and finds none."""
    del logger
    return page_problems(root, service, source_folder)
