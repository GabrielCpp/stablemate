"""Bounded thread pools, so one kind of blocking work cannot starve another."""
from __future__ import annotations

import asyncio
import functools
import logging
import os
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

logger = logging.getLogger("groom.pools")

_T = TypeVar("_T")

INGEST_WORKERS_DEFAULT = 4
QUERY_WORKERS_DEFAULT = 4


def _workers(env: str, default: int) -> int:
    """Worker count from the environment, floored at one."""
    raw = os.environ.get(env, "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        logger.warning("%s=%r is not an integer; using %d", env, raw, default)
        return default


class Pool:
    """One named executor, created on first use and disposed at shutdown."""

    def __init__(self, name: str, env: str, default: int) -> None:
        self.name = name
        self.env = env
        self.default = default
        self._executor: ThreadPoolExecutor | None = None
        self._lock = threading.Lock()

    @property
    def workers(self) -> int:
        return _workers(self.env, self.default)

    def executor(self) -> ThreadPoolExecutor:
        with self._lock:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(
                    max_workers=self.workers, thread_name_prefix=f"groom-{self.name}"
                )
            return self._executor

    async def run(self, fn: Callable[..., _T], /, *args: Any, **kwargs: Any) -> _T:
        """``asyncio.to_thread``, on this pool instead of the shared default one."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor(), functools.partial(fn, *args, **kwargs))

    def shutdown(self) -> None:
        """Drop the executor; the next :meth:`run` builds a fresh one."""
        with self._lock:
            executor, self._executor = self._executor, None
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)


INGEST = Pool("ingest", "GROOM_INGEST_WORKERS", INGEST_WORKERS_DEFAULT)
QUERY = Pool("query", "GROOM_QUERY_WORKERS", QUERY_WORKERS_DEFAULT)

ALL = (INGEST, QUERY)


def shutdown_all() -> None:
    """on_shutdown hook: release both pools."""
    for pool in ALL:
        pool.shutdown()
