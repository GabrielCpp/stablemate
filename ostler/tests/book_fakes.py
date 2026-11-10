"""Doubles the book tests stand in for a surface."""

from __future__ import annotations

from datetime import date
from typing import Any

from ostler.book import Done, Model, Refusal, Stack


class Quiet:
    """A surface with nothing to start, stop or reset: a test overrides what it needs."""

    name = "fake"

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def reset(self) -> None:
        return None

    def perform(self, step: Any) -> Done | Refusal:
        return Done()

    def rows(self) -> tuple[object, ...]:
        return ()


def no_stack(directory: str) -> Stack:
    return Stack((), directory)


class Counter(Model):
    """A model that keeps one number and adds one for every step `counts` accepts."""

    def __init__(self, today: date, n: int = 0) -> None:
        super().__init__(today)
        self.n = n

    def counts(self, request: object) -> bool:
        raise NotImplementedError

    def apply(self, request: object) -> tuple[object, ...] | None:
        if self.counts(request):
            self.n += 1
        return None

    def rows(self) -> tuple[object, ...]:
        return (self.n,)

    def copy(self) -> Counter:
        return type(self)(self.today, self.n)
