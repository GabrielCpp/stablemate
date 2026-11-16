"""Rules over every entry of a list: a property the entries hold whatever records the list holds, so it is judged on an
environment full of other people's data. A rule is any callable that takes the entries and returns what breaks it, and
its docstring's first line is what a book says of it. The same rules judge the entries a screen shows and the entries a
call answers."""

from __future__ import annotations

from typing import Any, Callable

Key = None | str | Callable[[Any], Any]


def says(rule: Callable[[list[Any]], list[str]]) -> str:
    """The first line of a rule's docstring: what a book says of it."""
    return (rule.__doc__ or "").strip().splitlines()[0] if (rule.__doc__ or "").strip() else ""


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


def of_pairs(rule: Callable[[list[Any]], list[str]]) -> Callable[[list[Any]], list[str]]:
    """Hands a rule the entries of a generated form as the pairs of accessible name and ARIA role it reads them as, where a
    rule on its own judges the names."""

    def judged(entries: list[Any]) -> list[str]:
        return rule(entries)

    judged.__doc__ = rule.__doc__
    setattr(judged, "pairs", True)
    return judged


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


def _short(entry: Any) -> str:
    text = repr(entry)
    return text if len(text) <= 120 else text[:120] + "..."


def has(key: str) -> Callable[[list[Any]], list[str]]:
    path = key.split(".")

    def rule(entries: list[Any]) -> list[str]:
        out: list[str] = []
        for position, entry in enumerate(entries):
            value = entry
            for part in path:
                value = value.get(part) if isinstance(value, dict) else None
            if value is None or value == "" or value == [] or value == {}:
                out.append(f"entry {position} has no {key}: {_short(entry)}")
        return out

    rule.__doc__ = f"every entry has {key}"
    return rule
