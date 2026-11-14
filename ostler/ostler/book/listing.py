"""The account of the selects a book's screens declare: which state what they hold and were judged by a pick,
which state it and no pick reached, and which only name the select."""

from __future__ import annotations

from typing import Any, Callable, Iterable, cast

from ostler.book.screen import Screen


def read_by(surface: Any) -> frozenset[str]:
    """The lists, by screen and attribute, a pick on the surface judged."""
    ask = getattr(surface, "lists_read", None)
    return frozenset(cast(Callable[[], Iterable[str]], ask)()) if callable(ask) else frozenset()


def account(screens: tuple[type[Screen], ...], read: frozenset[str]) -> list[str]:
    """The heading `Lists` and a line per select under three headings, or nothing when no screen has a select."""
    judged: list[str] = []
    unread: list[str] = []
    named: list[str] = []
    for screen in screens:
        for attribute, component in screen.attributes():
            if component.kind != "select":
                continue
            where = f"{screen.__name__}.{attribute}"
            if component.lists is not None:
                (judged if where in read else unread).append(where)
            elif not component.options:
                named.append(where)
    if not (judged or unread or named):
        return []
    out = ["Lists"]
    for heading, found in (("stated and read", judged), ("stated and never read", unread), ("named only", named)):
        out.append(f"{heading}:")
        out += [f"- {where}" for where in found] or ["- none"]
    return out
