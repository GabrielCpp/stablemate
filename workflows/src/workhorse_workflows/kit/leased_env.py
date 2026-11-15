"""The one module that writes the process environment: a QA lease's variables, for the length of a block."""
from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator, Mapping


@contextlib.contextmanager
def scoped_env(name: str, value: str) -> Iterator[None]:
    """Set ``name=value`` in the process environment for the block, then restore it."""
    previous = os.environ.get(name)
    os.environ[name] = value
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous


@contextlib.contextmanager
def scoped_envs(values: Mapping[str, str]) -> Iterator[None]:
    """`scoped_env` over several names at once, restored in reverse on exit."""
    with contextlib.ExitStack() as stack:
        for name, value in values.items():
            stack.enter_context(scoped_env(name, value))
        yield
