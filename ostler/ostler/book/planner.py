"""Breadth-first search over the model's state graph: which actions take the
app from where it is to where the user wants it."""

from __future__ import annotations

from collections import deque
from typing import Callable, Hashable, Iterable

from ostler.book.model import Flaw, Model, Refused


def plan(
    start: Model,
    goal: Callable[[Model], bool],
    moves: Callable[[Model], Iterable[object]],
    max_depth: int = 8,
) -> list[object] | None:
    seen: set[Hashable] = {start.key()}
    queue: deque[tuple[Model, list[object]]] = deque([(start, [])])
    while queue:
        state, path = queue.popleft()
        if goal(state):
            return path
        if len(path) >= max_depth:
            continue
        for move in moves(state):
            after = state.copy()
            try:
                after.apply(move)
            except (Refused, Flaw):
                continue
            key = after.key()
            if key in seen:
                continue
            seen.add(key)
            queue.append((after, path + [move]))
    return None
