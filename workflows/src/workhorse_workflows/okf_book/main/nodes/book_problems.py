"""The page check as the node the main flow calls, so a dry run can stand in for it."""
from __future__ import annotations

import logging
from pathlib import Path

from workhorse_workflows.okf_book.shared.blockers import Blocker
from workhorse_workflows.okf_book.shared.blueprint import blueprint
from workhorse_workflows.okf_book.shared.page_check import PageProblem, page_problems, tool_blockers
from workhorse_workflows.okf_book.shared.source_repo import SourceRepo


def _clean_in_dry_run(_logger: logging.Logger, *_args: object) -> tuple[PageProblem, ...]:
    return ()


def _no_tools_in_dry_run(_logger: logging.Logger, *_args: object) -> tuple[Blocker, ...]:
    return ()


@blueprint.node(stub=_clean_in_dry_run)
def book_problems(logger: logging.Logger, root: Path, service: str, source_folder: str, source: SourceRepo) -> tuple[PageProblem, ...]:
    """Every problem on the service's book, given its source folder in the source repository. A dry run reads no page and finds none."""
    del logger
    return page_problems(root, service, source_folder, source)


@blueprint.node(stub=_no_tools_in_dry_run)
def unopted_tools(logger: logging.Logger, root: Path, service: str, source: SourceRepo) -> tuple[Blocker, ...]:
    """One blocker per program the book's command pages name that the source repository opts in as no QA tool. A dry run loads no graph and finds none."""
    del logger
    return tool_blockers(root, service, source.path)
