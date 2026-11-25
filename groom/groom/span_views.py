"""Views built from one run's cached span list, built once per list and shared by every reader."""

from __future__ import annotations

import functools
import threading
from collections.abc import Callable
from typing import Any, TypeVar

_T = TypeVar("_T")


class SpanList(list):
    """A run's spans oldest first, and the views computed from exactly these spans. Every reader shares one list, so neither the list nor a view is changed in place."""

    def __init__(self, spans: list[dict[str, Any]]) -> None:
        super().__init__(spans)
        self.views: dict[Any, Any] = {}
        self.lock = threading.Lock()


def view(spans: list[dict[str, Any]], key: Any, build: Callable[[], _T]) -> _T:
    """``build()`` once per cached span list and ``key``, and on every call for a list the cache did not hand out."""
    if not isinstance(spans, SpanList):
        return build()
    with spans.lock:
        if key in spans.views:
            return spans.views[key]
    found = build()
    with spans.lock:
        return spans.views.setdefault(key, found)


def per_span_list(fn: Callable[[list[dict[str, Any]]], _T]) -> Callable[[list[dict[str, Any]]], _T]:
    """``fn`` built once per cached span list."""

    @functools.wraps(fn)
    def wrapper(spans: list[dict[str, Any]]) -> _T:
        return view(spans, fn, lambda: fn(spans))

    return wrapper
