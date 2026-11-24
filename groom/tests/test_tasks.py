"""A background task that dies is logged at error level with its traceback; a cancelled or finished one is silent."""
from __future__ import annotations

import asyncio
import logging

from groom import tasks


def _died(caplog):
    return [r for r in caplog.records if r.levelno >= logging.ERROR]


async def _finished(task: asyncio.Task) -> None:
    await asyncio.wait({task}, timeout=30)
    assert task.done()
    await asyncio.sleep(0)


def test_a_spawned_coroutine_that_raises_is_logged_with_its_name(caplog):
    async def boom():
        raise OSError("Too many open files")

    async def drive():
        task = tasks.spawn(boom(), name="the-doomed-job")
        await _finished(task)

    with caplog.at_level(logging.ERROR, logger="groom.tasks"):
        asyncio.run(drive())
    records = _died(caplog)
    assert len(records) == 1
    assert "the-doomed-job" in records[0].getMessage()
    assert isinstance(records[0].exc_info[1], OSError)


def test_a_cancelled_task_is_not_logged(caplog):
    async def forever():
        await asyncio.Event().wait()

    async def drive():
        task = tasks.spawn(forever(), name="the-cancelled-job")
        await asyncio.sleep(0)
        task.cancel()
        await _finished(task)

    with caplog.at_level(logging.ERROR, logger="groom.tasks"):
        asyncio.run(drive())
    assert _died(caplog) == []


def test_a_task_that_returns_is_not_logged(caplog):
    async def fine():
        return 3

    async def drive():
        task = tasks.spawn(fine(), name="the-fine-job")
        await _finished(task)
        return task.result()

    with caplog.at_level(logging.ERROR, logger="groom.tasks"):
        assert asyncio.run(drive()) == 3
    assert _died(caplog) == []
