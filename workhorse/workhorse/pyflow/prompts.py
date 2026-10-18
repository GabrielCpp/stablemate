"""A prompt helper that tells the static graph reader which path it resolves to."""
from __future__ import annotations

from collections.abc import Callable
from typing import Generic, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


class PromptResolver(Generic[P, R]):
    """A helper a state binds a local to, whose prompt path a static read names from the call's string literals."""

    def __init__(self, fn: Callable[P, R], path_of: Callable[..., str]) -> None:
        self._fn = fn
        self._path_of = path_of
        self.__doc__ = fn.__doc__
        self.__name__ = getattr(fn, "__name__", type(fn).__name__)
        self.__wrapped__ = fn

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        return self._fn(*args, **kwargs)

    def prompt_path(self, cls: type, *literals: str) -> str:
        """The path the helper resolves to for `cls`, given the string literals its call was written with."""
        return self._path_of(cls, *literals)


def resolves_prompt(
    path_of: Callable[..., str],
) -> Callable[[Callable[P, R]], PromptResolver[P, R]]:
    """Mark a helper whose result a state passes to `self.agent(...)`.

    `path_of(cls, *literals)` receives the workflow class and the string constants of the
    call, in order, and returns the prompt path the helper would resolve at run time. The
    graph reader, `dot` and `--dry-run` then name that prompt instead of reporting a local
    they cannot read.
    """

    def wrap(fn: Callable[P, R]) -> PromptResolver[P, R]:
        return PromptResolver(fn, path_of)

    return wrap


__all__ = ["PromptResolver", "resolves_prompt"]
