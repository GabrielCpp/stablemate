"""The judgement of a list a surface has read: the texts it shows and the entry it has selected, against what the
book says it holds. A surface reads the list its own way and names the feed its way. This module knows neither."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from ostler.book.screen import Component, Lists, Screen


class Unfed(Exception):
    """The data a list is derived from cannot be had, and why: the whole text is the fault."""


Feed = Callable[[Component, str], Any]


class ListJudge:
    def __init__(self) -> None:
        self.screens: tuple[type[Screen], ...] = ()
        self.faults: list[str] = []
        self.read: dict[str, set[str]] = {}
        self.picked: set[str] = set()
        self.expected: dict[str, tuple[Any, ...]] = {}

    def feeding(self, screens: tuple[type[Screen], ...]) -> None:
        self.screens = screens

    def taken(self) -> list[str]:
        """The differences found since the last time this was asked."""
        faults, self.faults = self.faults, []
        return faults

    def lists_read(self) -> frozenset[str]:
        return frozenset(self.read)

    def claims_judged(self) -> dict[str, frozenset[str]]:
        return {name: frozenset(claims) for name, claims in self.read.items()}

    def forget_picks(self) -> None:
        self.picked.clear()

    def expecting(self, expectations: Mapping[str, tuple[Any, ...]]) -> None:
        self.expected = dict(expectations)

    def named(self, component: Component, lang: str) -> str:
        for screen in self.screens:
            for name, found in screen.attributes():
                if found is component:
                    return f"{screen.__name__}.{name}"
        return component.found_by(lang)

    def judge(self, component: Component, shown: list[str], selected: str, lang: str, feed: Feed) -> None:
        lists = component.lists
        assert lists is not None
        name = self.named(component, lang)
        judged = self.read.setdefault(name, set())
        if lists.derived is not None:
            judged.add("derived")
            self.derived(component, name, shown, lang, feed)
        self.entries(lists, name, shown, lang)
        if lists.entries:
            judged.add("entries")
        self.picked_entry(lists, name, selected, lang)
        if name not in self.picked and (lists.picked is not None and (not callable(lists.picked) or len(self.expected.get(name, ())) > 2)):
            judged.add("picked")
        self.picked.add(name)
        belong, never = self.expected.get(name, ([], []))[:2]
        if lists.always is not None and name in self.expected:
            judged.add("always")
        if lists.never is not None and name in self.expected:
            judged.add("never")
        missing = [text for text in dict.fromkeys(belong) if text not in shown]
        if missing:
            self.faults.append(f"the list {name} misses {missing}, which belong in it")
        forbidden = [text for text in dict.fromkeys(never) if text in shown]
        if forbidden:
            self.faults.append(f"the list {name} shows {forbidden}, which must never be in it")

    def entries(self, lists: Lists, name: str, shown: list[str], lang: str) -> None:
        head = lists.labels(lang)
        entries = shown[len(head):] if shown[:len(head)] == head else shown
        for rule in lists.entries:
            said = (rule.__doc__ or "").strip().splitlines()[0]
            try:
                broken = rule(entries)
            except Exception as crash:
                self.faults.append(f"the list {name} cannot judge \"{said}\": {type(crash).__name__}: {crash}")
                continue
            self.faults += [f"the list {name} breaks \"{said}\": {why}" for why in broken]

    def picked_entry(self, lists: Lists, name: str, selected: str, lang: str) -> None:
        if name in self.picked or lists.picked is None:
            return
        expected = self.expected.get(name, ())
        wanted = lists.label_picked(lang) if not callable(lists.picked) else expected[2] if len(expected) > 2 else None
        if wanted is not None and selected != wanted:
            self.faults.append(f"the list {name} has {selected!r} selected before the pick, the book says {wanted!r}")

    def derived(self, component: Component, name: str, shown: list[str], lang: str, feed: Feed) -> None:
        lists = component.lists
        assert lists is not None and lists.given is not None and lists.derived is not None
        try:
            body = feed(component, name)
        except Unfed as unfed:
            self.faults.append(str(unfed))
            return
        derived = [*lists.labels(lang), *lists.derived(body)]
        if shown != derived:
            self.faults.append(f"the list {name} shows {shown}, the book derives {derived}")
