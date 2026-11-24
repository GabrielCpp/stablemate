from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from types import ModuleType
from unittest.mock import patch

from groom import live

DEADLINE_S = 30.0


async def until(done: Callable[[], bool], what: str) -> None:
    deadline = time.monotonic() + DEADLINE_S
    while not done():
        if time.monotonic() > deadline:
            raise AssertionError(f"{what} did not happen within {DEADLINE_S:.0f} s")
        await asyncio.sleep(0.005)


async def settled() -> None:
    await asyncio.sleep(0)
    await until(lambda: not live.pending(), "the push going quiet")


@contextmanager
def watch_started(module: ModuleType, passed: list[str] | None = None) -> Iterator[asyncio.Event]:
    """Set the event once `module`'s watch is live, and list in `passed` each path the watch let through."""
    started = asyncio.Event()
    real = module.awatch

    async def watch(*paths, **options):
        started.set()
        async for changes in real(*paths, **options):
            if passed is not None:
                passed.extend(path for _, path in changes)
            yield changes

    with patch.object(module, "awatch", watch):
        yield started
