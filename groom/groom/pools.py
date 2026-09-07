"""Bounded thread pools, so one kind of blocking work cannot starve another.

Every blocking call in this process used to go to the event loop's default
executor, which asyncio sizes at ``min(32, cpu_count + 4)`` — twelve threads on
an eight-core box. Telemetry ingest shared those twelve with ``turns.harvest``
(a bulk file copy), ``discovery.scan`` and the docker subprocesses it shells
out to, the workspace-volume readers, and desktop notifications.

That is fine until one of them is slow, and on a host running a fleet of
concurrent workflows one of them always is. A handful of docker calls waiting on
a saturated disk take every slot; from then on *every* later ``to_thread``
queues, however trivial. The collector stops storing, and — because the
dashboard's own live tick reaches the store through the same pool — it also
stops sending frames, so the browser reads the silence as a dead connection and
the whole UI goes unresponsive while plain GETs still answer in milliseconds.

The fix is isolation, not size. Telemetry ingest gets its own pool and the
dashboard's store reads get theirs, so neither can be crowded out by work that
has nothing to do with them. Slow, unbounded and unpredictable work — docker,
the filesystem, notifications — stays on the default executor, which is exactly
where something that may block for a minute belongs.

The pools are deliberately small. Writes serialise on the store's single
connection anyway, so extra threads buy queueing rather than throughput; what
the pool is for is a ceiling that belongs to one concern.
"""
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
    """Worker count from the environment, floored at one.

    A pool of zero is a deadlock rather than a configuration, so an unreadable
    or absurd value falls back rather than being taken literally.
    """
    raw = os.environ.get(env, "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        logger.warning("%s=%r is not an integer; using %d", env, raw, default)
        return default


class Pool:
    """One named executor, created on first use and disposed at shutdown.

    Lazy because the size is read from the environment: a test that sets
    ``GROOM_INGEST_WORKERS`` gets the pool it asked for, rather than one sized
    at import time by whatever the environment happened to be then.
    """

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
        """Drop the executor; the next :meth:`run` builds a fresh one.

        ``wait=False`` on purpose — shutdown must not block on a store call that
        is itself waiting on the disk that made the process unresponsive.
        """
        with self._lock:
            executor, self._executor = self._executor, None
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)


#: OTLP ingest — the span/metric/log writes the collector must keep accepting.
INGEST = Pool("ingest", "GROOM_INGEST_WORKERS", INGEST_WORKERS_DEFAULT)
#: Store reads serving the dashboard and the live tick, whose stalling is what
#: the operator actually sees.
QUERY = Pool("query", "GROOM_QUERY_WORKERS", QUERY_WORKERS_DEFAULT)

ALL = (INGEST, QUERY)


def shutdown_all() -> None:
    """on_shutdown hook: release both pools."""
    for pool in ALL:
        pool.shutdown()
