"""Typed reads of a task's declared inputs."""

from __future__ import annotations

from paddock.runner import Run


def names(run: Run, key: str) -> tuple[str, ...]:
    """The strings the task declared under *key*, empty when it declared none."""
    value = run.inputs.get(key)
    if value is None:
        return ()
    if isinstance(value, list):
        return tuple(value)
    if isinstance(value, str):
        return tuple(part for part in value.split(",") if part)
    raise TypeError(f"input {key!r} is {type(value).__name__}, expected a list of strings")


def number(run: Run, key: str, default: float) -> float:
    """The number the task declared under *key*, or *default*."""
    value = run.inputs.get(key)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise TypeError(f"input {key!r} is {type(value).__name__}, expected a number")
    return float(value)


def flag(run: Run, key: str, default: bool = False) -> bool:
    """The boolean the task declared under *key*, or *default*."""
    value = run.inputs.get(key)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise TypeError(f"input {key!r} is {type(value).__name__}, expected a boolean")
    return value
