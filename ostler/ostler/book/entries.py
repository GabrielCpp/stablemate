"""Rules over every entry of a list: a property the entries hold whatever records the list holds, so it is judged on an
environment full of other people's data. A rule is any callable that takes the entries and returns what breaks it, and
its docstring's first line is what a book says of it. The same rules judge the entries a screen shows and the entries a
call answers."""

from __future__ import annotations

from typing import Any, Callable

Key = None | str | Callable[[Any], Any]


def _read(key: Key) -> Callable[[Any], Any]:
    if key is None:
        return lambda entry: entry
    if not isinstance(key, str):
        return key
    path = key.split(".")

    def field(entry: Any) -> Any:
        for part in path:
            entry = entry[part]
        return entry

    return field


def _named(key: Key) -> str:
    return "" if key is None else key if isinstance(key, str) else getattr(key, "__name__", "a function")


def in_order(key: Key = None) -> Callable[[list[Any]], list[str]]:
    read = _read(key)

    def rule(entries: list[Any]) -> list[str]:
        for ahead, entry in zip(entries, entries[1:]):
            if read(entry) < read(ahead):
                return [f"{entry!r} comes after {ahead!r}"]
        return []

    named = _named(key)
    rule.__doc__ = f"in order of {named}" if named else "in order"
    return rule


def no_repeat(key: Key = None) -> Callable[[list[Any]], list[str]]:
    read = _read(key)

    def rule(entries: list[Any]) -> list[str]:
        counts: dict[str, list[Any]] = {}
        for entry in entries:
            value = read(entry)
            counts.setdefault(repr(value), [value, 0])[1] += 1
        return [f"{value!r} is shown {count} times" for value, count in counts.values() if count > 1]

    named = _named(key)
    rule.__doc__ = f"no repeat of {named}" if named else "no repeat"
    return rule
