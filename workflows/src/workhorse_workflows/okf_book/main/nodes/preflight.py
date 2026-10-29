"""The check before a run's first writer turn: each declared stack comes up once and is released at once."""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from pathlib import Path

from workhorse_workflows.okf_book.shared.book_run import StackReadiness, release, stack_pages
from workhorse_workflows.okf_book.shared.entries import SERVICES_DIR

_LOGGER = logging.getLogger(__name__)


def down_stack(root: Path, services: Iterable[str], bring_up: Callable[[Path, str], StackReadiness]) -> tuple[str, str] | None:
    """The first service whose declared stack does not come up, with why. A service with no book folder yet, or whose book declares no stack, is skipped."""
    for service in services:
        if not (root / SERVICES_DIR / service).is_dir() or not stack_pages(root, service):
            continue
        stack = bring_up(root, service)
        release(_LOGGER, stack)
        if not stack.up:
            return service, stack.notes
    return None
