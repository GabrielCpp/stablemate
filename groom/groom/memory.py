"""Hand freed heap back to the operating system after a pooled job that read a large run."""
from __future__ import annotations

import ctypes
import functools
import sys
import threading
from collections.abc import Callable
from typing import Any, TypeVar, cast

_T = TypeVar("_T")

LARGE_READ_SPANS = 5000

_noted = threading.local()


def note_read(spans: int) -> None:
    """Mark this thread's job as one that read ``spans`` spans, so it trims when it ends if that is a large read."""
    if spans >= LARGE_READ_SPANS:
        _noted.large = True


@functools.cache
def _trimmer() -> Callable[[int], int] | None:
    if not sys.platform.startswith("linux"):
        return None
    try:
        libc = ctypes.CDLL(None)
    except OSError:
        return None
    trim = getattr(libc, "malloc_trim", None)
    if trim is None:
        return None
    trim.argtypes = [ctypes.c_size_t]
    trim.restype = ctypes.c_int
    return cast("Callable[[int], int]", trim)


def release() -> bool:
    """Ask the allocator to return free heap to the operating system. False where it cannot."""
    trim = _trimmer()
    if trim is None:
        return False
    trim(0)
    return True


def trimmed(fn: Callable[..., _T], /, *args: Any, **kwargs: Any) -> _T:
    """Run ``fn`` and release freed heap afterwards when it noted a large read."""
    _noted.large = False
    try:
        return fn(*args, **kwargs)
    finally:
        if getattr(_noted, "large", False):
            _noted.large = False
            release()
