"""A pooled job that read a large run hands the freed heap back once."""
from __future__ import annotations

import asyncio

import pytest

from groom import memory, pools, store
from tests.test_row_figures import _DB, _span


def _seed(count: int) -> None:
    store.insert_spans([_span(f"s{index}", "", "qa", "qa", {}, 100.0 + index, 1) for index in range(count)])


def _recorder(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    seen: list[int] = []
    monkeypatch.setattr(memory, "_trimmer", lambda: seen.append)
    return seen


def _run(fn, *args):
    async def go():
        try:
            return await pools.QUERY.run(fn, *args)
        finally:
            pools.shutdown_all()

    return asyncio.run(go())


def test_a_pooled_large_read_trims_the_heap_once(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _recorder(monkeypatch)
    monkeypatch.setattr(memory, "LARGE_READ_SPANS", 2)
    with _DB():
        _seed(3)
        _run(store.run_turn_spans, "run-1")
        assert seen == [0]
        _run(store.run_turn_spans, "other")
        assert seen == [0]


def test_release_is_a_no_op_off_glibc(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(memory.sys, "platform", "darwin")
    memory._trimmer.cache_clear()
    try:
        assert memory._trimmer() is None
        assert memory.release() is False
    finally:
        memory._trimmer.cache_clear()


def test_a_job_that_raises_still_resets_the_mark(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _recorder(monkeypatch)

    def big_then_fail() -> None:
        memory.note_read(10**6)
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        _run(big_then_fail)
    assert seen == [0]
    _run(lambda: memory.note_read(1))
    assert seen == [0]
