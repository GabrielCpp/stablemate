"""Holding the store lock from another thread, shared by the tests that prove a call does not queue for it."""
from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from groom import store

HOLD_S = 30.0


@contextmanager
def lock_held() -> Iterator[None]:
    """Hold the process-wide store lock from another thread for the block, and refuse a block that only ended once the hold gave up."""
    holding = threading.Event()
    release = threading.Event()
    released: list[bool] = []

    def hold() -> None:
        with store.STORE.lock:
            holding.set()
            released.append(release.wait(HOLD_S))

    thread = threading.Thread(target=hold, daemon=True)
    thread.start()
    assert holding.wait(HOLD_S), "the holder thread never acquired the store lock"
    try:
        yield
    finally:
        release.set()
        thread.join(HOLD_S)
    assert released == [True], "a call in the block queued for the store lock until the holder gave it up"
