from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

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
