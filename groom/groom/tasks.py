"""Background tasks whose result nobody awaits: a death is logged at error level instead of waiting for garbage collection."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger(__name__)


def report(task: asyncio.Task[object]) -> None:
    """Done callback: log the exception a finished task died with, and stay silent for a cancelled or a clean one."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("groom: background task %s died", task.get_name(), exc_info=exc)


def spawn[T](coro: Coroutine[Any, Any, T], *, name: str) -> asyncio.Task[T]:
    """Start ``coro`` as a named task whose death is reported."""
    task = asyncio.create_task(coro, name=name)
    task.add_done_callback(report)
    return task
