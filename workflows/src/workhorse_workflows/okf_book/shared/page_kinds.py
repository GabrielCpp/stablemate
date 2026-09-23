"""What a book page is to aggregation, read off its frontmatter type.

An operations page or a flow page is written with every other page of its kind in one job. Any other
page is written by a job of its own.
"""
from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path

from workhorse_workflows.okf_book.shared.citations import book_pages

_CONCEPT = re.compile(r"^type:\s*concept\s*$", re.MULTILINE)
_OPERATIONS = re.compile(r"^type:\s*(runbook|environment|step|fixture)\s*$", re.MULTILINE)
_FLOW = re.compile(r"^type:\s*flow\s*$", re.MULTILINE)


class JobKind(StrEnum):
    """What an aggregation turn writes: one page, the pages that run the stack, or the flows."""

    PAGE = "page"
    OPERATIONS = "operations"
    FLOWS = "flows"


def page_kind(text: str) -> JobKind:
    """The kind of job that writes a page with this text."""
    if _OPERATIONS.search(text):
        return JobKind.OPERATIONS
    if _FLOW.search(text):
        return JobKind.FLOWS
    return JobKind.PAGE


def is_concept(text: str) -> bool:
    return bool(_CONCEPT.search(text))


def pages_of_kind(root: Path, service: str, kind: JobKind) -> tuple[str, ...]:
    """The service's pages a job of `kind` writes, repo-relative."""
    return tuple(
        page.resolve().relative_to(root.resolve()).as_posix()
        for page in book_pages(root, service)
        if page_kind(page.read_text(encoding="utf-8")) is kind
    )
